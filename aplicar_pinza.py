#!/usr/bin/env python3
"""aplicar_pinza.py - conecta la pinza y la lectura de angulos REALES al arm_broker.

Que arregla (error 9 de la guia): /arm/pinza no tenia publicador porque _gripper era un
stub. Despues de aplicarlo:
  * arm_broker publica Int32 (0..100) en /arm/pinza, SOLO desde el worker.
  * Con habilitar_gripper=false NO publica nada: solo lo anota en el log (modo seguro).
  * arm_broker se suscribe a /arm/angulos_medidos (std_msgs/Float64MultiArray, 6 valores
    en RADIANES) para calcular error_fk_mm con los angulos reales y no con los comandados.
    Si nadie publica ahi, el error se calcula sobre q comandado y queda marcado como tal.

Uso (desde la raiz del workspace):
    cd ~/gran_reto_ws_v2
    python3 aplicar_pinza.py
    colcon build --symlink-install --packages-select arm_broker && source install/setup.bash

Es idempotente (si ya esta aplicado no hace nada) y guarda broker_node.py.bak_pinza.
"""
import os
import re
import shutil
import sys

RUTA = os.path.join('src', 'arm_broker', 'arm_broker', 'broker_node.py')


def reemplazar_una_vez(src, viejo, nuevo, nombre):
    n = src.count(viejo)
    if n != 1:
        sys.exit('ABORTO: el ancla "%s" aparece %d veces (se esperaba 1). El broker_node.py no es '
                 'el que se uso para escribir este parche; no se modifico nada.' % (nombre, n))
    return src.replace(viejo, nuevo, 1)


BLOQUE_INIT = '''        # ---- pinza y angulos medidos (aplicar_pinza.py) ----
        self._pinza_abierta, self._pinza_cerrada = int(p('pinza_abierta')), int(p('pinza_cerrada'))
        self._pinza_espera, self._q_real_espera = float(p('pinza_espera_s')), float(p('q_real_espera_s'))
        self._q_real_edad_max = float(p('q_real_max_edad_s'))
        self._q_med, self._q_med_t, self._qmed_lock = None, 0.0, threading.Lock()
        self._pinza_pub = self.create_publisher(Int32, '/arm/pinza', 10)   # solo el worker publica aqui
        self.create_subscription(Float64MultiArray, '/arm/angulos_medidos', self._on_q_medido, 10,
                                 callback_group=ReentrantCallbackGroup())
'''

METODOS_NUEVOS = '''    def _gripper(self, accion):
        """accion: 'abrir' | 'cerrar'. Solo el worker llega aqui => /arm/pinza tiene UN publicador."""
        valor = self._pinza_abierta if accion == 'abrir' else self._pinza_cerrada
        if not bool(self.get_parameter('habilitar_gripper').value):   # se lee en vivo: ros2 param set
            self.get_logger().info(f'[GRIPPER] {accion} ({valor}) NO enviado: habilitar_gripper=false')
            time.sleep(0.3)
            return
        self._pinza_pub.publish(Int32(data=int(valor)))
        self.get_logger().info(f'[GRIPPER] {accion} -> /arm/pinza={valor}')
        time.sleep(self._pinza_espera)          # deja que la pinza termine antes del siguiente paso

    def _on_q_medido(self, msg):
        """Callback del driver (otro hilo): guarda la ultima lectura de angulos reales (rad)."""
        if len(msg.data) >= 6:
            with self._qmed_lock:
                self._q_med, self._q_med_t = np.array(msg.data[:6], float), time.monotonic()

    def _leer_q_real(self):
        """Angulos REALES del brazo (rad) desde /arm/angulos_medidos; None si no hay lectura fresca."""
        if self._q_med is None:                  # nadie ha publicado: no esperes en vano
            return None
        time.sleep(self._q_real_espera)          # el brazo fisico llega despues que el comando
        with self._qmed_lock:
            q, t = self._q_med, self._q_med_t
        if q is None or time.monotonic() - t > self._q_real_edad_max:
            return None
        return q.copy()

'''


def main():
    if not os.path.isfile(RUTA):
        sys.exit('No encuentro %s. Ejecuta este script desde la raiz del workspace (~/gran_reto_ws_v2).' % RUTA)
    with open(RUTA, encoding='utf-8') as f:
        src = f.read()
    if '_pinza_pub' in src:
        print('Ya estaba aplicado (_pinza_pub existe). No se cambia nada.')
        return

    src = reemplazar_una_vez(
        src, 'from std_msgs.msg import String\n',
        'from std_msgs.msg import Float64MultiArray, Int32, String\n', 'import std_msgs')
    src = reemplazar_una_vez(
        src, '                habilitar_gripper=False).items():',
        '                habilitar_gripper=False, pinza_abierta=100, pinza_cerrada=15,\n'
        '                pinza_espera_s=0.8, q_real_espera_s=0.8, q_real_max_edad_s=1.0).items():',
        'declaracion de parametros de _init_pick')
    src = reemplazar_una_vez(
        src, "        self._mesa = Mesa.desde_params(list(p('mesa_objetos')), list(p('mesa_zonas')))\n",
        BLOQUE_INIT + "        self._mesa = Mesa.desde_params(list(p('mesa_objetos')), list(p('mesa_zonas')))\n",
        'creacion de la mesa')

    m = re.search(r'    def _gripper\(self, accion\):.*?(?=    def _fila_desglose)', src, re.S)
    if not m or src.count('    def _gripper(self, accion):') != 1 or src.count('    def _fila_desglose') != 1:
        sys.exit('ABORTO: no encuentro los ganchos _gripper/_leer_q_real con la forma esperada.')
    src = src[:m.start()] + METODOS_NUEVOS + src[m.end():]

    shutil.copy2(RUTA, RUTA + '.bak_pinza')
    with open(RUTA, 'w', encoding='utf-8') as f:
        f.write(src)
    try:
        compile(src, RUTA, 'exec')
    except SyntaxError as e:
        shutil.copy2(RUTA + '.bak_pinza', RUTA)
        sys.exit('El resultado no compila (%s). Se restauro el original.' % e)

    print('OK. broker_node.py actualizado (respaldo: %s.bak_pinza).' % RUTA)
    print('Siguiente: grep -c _pinza_pub %s   (debe dar 3 o mas)' % RUTA)
    print('           colcon build --symlink-install --packages-select arm_broker && source install/setup.bash')


if __name__ == '__main__':
    main()
