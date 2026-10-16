# Gran Reto JetCobot — sobre el broker RB-2 (ROS 2 Humble)

## Paquetes (`src/`)
| Paquete | Origen | Qué contiene |
|---|---|---|
| `arm_broker_interfaces` | **tu RB-2** + 1 acción | `MoveJoints`, `QueueState` (sin tocar) + **`PickPlace.action`** (nueva) |
| `arm_broker` | **tu RB-2** extendido (ver `cambios_en_rb2.patch`) | tu broker, admisión, políticas y FK; **+** `ik.py`, `pick_place.py` y la 2.ª acción `/arm/pick_place` |
| `jetcobot_interfaces` | nuevo | `InterpretarOrden.srv` |
| `gran_reto_jetcobot` | nuevo | `interprete_ordenes` (único que habla con LAYA), `transcriptor_voz`, `cliente_ordenes`, `medir_latencia`, `laya_falso` |

## Qué cambió en tu RB-2 (todo aditivo)
- `policies.py`: 3 campos nuevos al final de `Entry` (con valor por defecto; tus tests siguen pasando).
- `broker_node.py`: 2.º `ActionServer` sobre la **misma cola, mismo worker y mismo portero**; el worker
  despacha con un `elif e.kind == 'pick'` y sigue publicando **solo** por `_publish_joint_state`.
- Tu `MoveJoints`, tus políticas (`fifo|priority|aging|rr`) y tu `/arm/queue_state` quedan igual.

## Reglas del examen
1. Solo `interprete_ordenes` habla con LAYA.  2. Solo `arm_broker` publica `/joint_states`.
3. `permitido=false` se rechaza en el `goal_callback`, antes de encolar, con causa en `/arm/rejections` y `rechazos.csv`.
4. La prioridad sale del modelo (`1,2,3` → `0,1,2` del broker; **0 = más alta**).
5. Clave de Google solo en variable de entorno.

## ANTES de habilitar el brazo (calibración obligatoria)
`arm_broker_gran_reto.yaml` trae valores de EJEMPLO. Mide y cambia:
1. `mesa_objetos` / `mesa_zonas`: posiciones reales en **mm**, marco de la base.
2. `q_agarre_ref`: pon el brazo a mano con el gripper hacia la mesa y copia `mc.get_angles()` en **radianes**.
3. `eje_aproximacion`: eje (0=x, 1=y, 2=z) de `kinematics.fk` que apunta hacia el objeto. Compruébalo: en esa pose, `fk(q_ref)[:3, eje]` debe ser ≈ `[0, 0, -1]`.
4. `dz_agarre_mm`: longitud flange→punta del gripper.
Al arrancar, el broker avisa `ALCANCE: ...` si algo no es alcanzable.

## Ganchos pendientes (retos previos)
`_percibir` (cámara), `_gripper`, `_leer_q_real` en `broker_node.py`, y MoveIt2 si lo exige tu enunciado.

## Compilar y correr
    
    
    source install/setup.bash && export ROS_DOMAIN_ID=<el de tu equipo>
    mkdir -p ~/rb2_logs
    ros2 launch gran_reto_jetcobot gran_reto.launch.py laya_host:=<IP> laya_puerto:=<PUERTO> timeout_s:=2.0
    ros2 run gran_reto_jetcobot transcriptor_voz --ros-args -p origen:=ana     # voz
    ros2 run gran_reto_jetcobot cliente_ordenes  --ros-args -p origen:=luis    # texto

## Pruebas sin ROS
    cd src/arm_broker && python3 -m pytest test        # o los scripts de test_*.py
    cd src/gran_reto_jetcobot && python3 -m unittest discover -s test -v
