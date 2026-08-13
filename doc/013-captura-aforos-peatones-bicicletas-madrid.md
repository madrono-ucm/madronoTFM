# 013 — Captura de aforos de peatones y bicicletas de Madrid (muestra puntual)

## Qué se implementó

Duodécimo productor de datos de la Fase 1 (Ingesta), y complementario a la
tarea 012: donde `afluencia_lugares_madrid.py` estima popularidad tipo
Google para un lugar concreto vía una librería en zona gris académica, esta
fuente usa un **dato oficial del Ayuntamiento, sin ningún problema de
condiciones de uso** (licencia CC BY 4.0) — conteos horarios reales de
peatones y bicicletas en puntos y calles fijas de Madrid, medidos con
cámaras de visión artificial (tecnología Data From Sky).

- `ingesta/capturas/aforos_peatones_bicicletas_madrid.py`: descarga los
  conteos horarios de peatones y bicicletas de la red de estaciones
  permanentes de aforo del Ayuntamiento y los normaliza a un esquema mínimo
  y consistente. Sin bucle, sin `--interval-seconds`, sin `BronzeWriter`,
  igual que las tareas 003-008 y 012.
- `ingesta/capturas/samples/aforos_peatones_bicicletas_madrid_sample.json`:
  la muestra pequeña commiteada como fixture (36 registros reales: 3
  estaciones de peatones × 6 horas + 3 estaciones de bicicletas × 6 horas,
  del último día disponible en cada CSV de origen).
- `ingesta/tests/test_aforos_peatones_bicicletas_madrid.py` +
  `ingesta/tests/fixtures/aforos_peatones_sample.csv` +
  `aforos_bicicletas_sample.csv`: tests con `unittest` (sin red) que
  verifican el filtrado al último día real (incluyendo el caso, descubierto
  en esta tarea, de que el fichero está agrupado por estación y no por
  fecha — ver más abajo), el tope de estaciones/horas por muestra, la
  normalización de una lectura de peatones y de bicicletas, el caso de una
  estación sin distrito asignado, y que la muestra commiteada cumple el
  esquema esperado.
- `ingesta/README.md`: nueva sección para esta fuente (fuente elegida y por
  qué, formato real encontrado, la peculiaridad de agrupación por estación,
  la decisión de dos campos de conteo, variables de entorno, esquema, y la
  nota sobre la captura real en vivo).

## Fuente elegida y por qué

Dataset ["Aforos de peatones y bicicletas"](https://datos.madrid.es/dataset/300321-0-aforos-peatones-bicicletas)
(id `300321-0-aforos-peatones-bicicletas`) de datos.madrid.es, publicado por
la Dirección General de Planificación e Infraestructuras de Movilidad —
exactamente la fuente que sugería el objetivo de la tarea. Publica un CSV
independiente por año y por modo (peatones/bicicletas): 6 CSV de peatones y
6 de bicicletas (2019-2024), verificado en vivo vía la API CKAN del portal
(`package_search`/`package_show`). El propio dataset enlaza otros dos
("Aforos de tráfico... permanentes/no permanentes") que miden intensidad de
**vehículos**, no de peatones/bicicletas — fuera del alcance de esta tarea.

## Formato real encontrado y decisiones de diseño (por qué)

- **El recurso más reciente sigue siendo el de 2024, y solo cubre
  enero-junio**: pese a que los metadatos del dataset figuran como
  modificados el 2026-07-24 (fecha de esta captura: 2026-08-13), no existe
  ningún recurso 2025 ni 2026 (verificado en vivo). El propio CSV de 2024 es
  un acumulado trimestral que llega hasta el 30/06/2024 inclusive — un
  desfase de publicación notable que se documenta explícitamente para que
  una tarea futura no dé por hecho que el dato está al día. Se usa este
  recurso tal cual como fuente por defecto; si en el futuro hay uno más
  reciente, basta con apuntar
  `MADRID_COUNTERS_PEDESTRIAN_URL`/`MADRID_COUNTERS_BICYCLE_URL` a la nueva
  URL sin tocar código.
- **El CSV está agrupado por estación, no por fecha (hallazgo relevante de
  esta sesión)**: a diferencia del CSV diario de `ruido_madrid.py`
  (cronológico de forma global), aquí cada bloque contiguo del fichero es
  el histórico completo de una estación, ordenado por fecha dentro del
  bloque; luego viene el bloque de la siguiente estación. Un primer intento
  de reutilizar literalmente el patrón "cortar cuando cambia la fecha" de
  `parse_latest_day_entries` (tarea 007) produjo una muestra real pero
  **incorrecta**: solo 22 filas (las del último bloque/estación) en vez de
  las 712 reales del último día en todas las estaciones. Se corrigió con
  `parse_latest_day_rows`: un primer recorrido para hallar la fecha máxima
  real de todo el fichero, y un segundo filtrado por esa fecha. Se verificó
  en vivo que las 30 estaciones de peatones y las 53 de bicicletas
  comparten la misma última fecha (30/06/2024), así que el resultado sigue
  siendo "el último día, todas las estaciones". Este error se detectó y
  corrigió dentro de la misma sesión, antes de generar el fixture
  commiteado (que ya refleja el comportamiento correcto), y queda cubierto
  por un test dedicado
  (`test_keeps_only_rows_from_the_last_date_across_all_station_blocks`) que
  reproduce a propósito esta estructura agrupada.
- **Dos campos de conteo (`pedestrian_count`/`bicycle_count`), pero solo uno
  relleno por registro**: peatones y bicicletas se miden con redes de
  estaciones físicamente distintas (30 puntos `PERM_PEA##`, 53 puntos
  `PERM_BICI##`, casi siempre en calles diferentes) — no es el mismo punto
  midiendo dos magnitudes a la vez. El objetivo de la tarea pedía
  explícitamente ambos campos ("peatones contados, bicicletas contadas");
  se decidió incluir los dos en un único esquema común (con un campo `mode`
  indicando cuál aplica) en vez de forzar un cruce por ubicación/hora que
  habría inventado una relación que la fuente no da. Ambos modos comparten
  el mismo esquema, así que un consumidor puede tratar la muestra como un
  único dataset y filtrar por `mode` si necesita solo uno.
- **`hora` se descarta del esquema**: es redundante con la parte de hora de
  `fecha` (verificado sobre los ~130.000/~220.000 registros completos de
  ambos CSV de 2024: coincide en el 100% de las filas).
- **`device_id` se descarta del esquema**: siempre idéntico a
  `identificador` en ambos CSV completos (verificado en vivo); se conserva
  solo `station_id` (de `identificador`).
- **Latitud/longitud reutilizan el mismo parseo "agrupado por puntos" que
  `ruido_madrid.py`** (p.ej. `"40.417.386"` → `40.417386`): mismo formato de
  origen exacto, aunque son fuentes de datasets distintos del Ayuntamiento;
  se duplicó la función localmente (siguiendo la convención ya establecida
  en este proyecto de no compartir helpers entre módulos de captura) en vez
  de extraer un util común.
- **Sin `BronzeWriter` ni modo `--interval-seconds`, por la misma razón de
  alcance reducido que las tareas 003-008 y 012**: no hay infraestructura
  aplicada todavía (tarea 001 pendiente). A diferencia de las tareas 009-011
  (datos de referencia), esta fuente sí es candidata a productor continuo
  real en el futuro (aforos cambian con el tiempo, igual que tráfico o
  calidad del aire) — el `TODO(kafka)` del módulo aplica en el mismo
  sentido que en esos productores, no como el de las tareas de referencia.
- **Sin variables de entorno de credenciales**: ambos recursos de
  datos.madrid.es usados son públicos y no las requieren.

## Captura real en vivo

Se completó una **captura real en vivo**: el fixture commiteado son 36
registros reales (3 estaciones de peatones y 3 de bicicletas, 6 horas cada
una, del 30/06/2024, el último día disponible en ambos CSV), descargados
ejecutando `python3 -m ingesta.capturas.aforos_peatones_bicicletas_madrid`
tal cual contra ambos recursos públicos durante esta sesión — no son datos
de ejemplo generados a mano. Ambos CSV completos (~17 MB peatones, ~34 MB
bicicletas) se descargaron en memoria porque la fuente no ofrece filtrado
remoto ni un recurso más pequeño, pero en ningún momento se escribieron a
disco; solo la muestra final de 36 registros. La inspección previa del
dataset (tamaños, estructura, agrupación por estación) se hizo con `curl`,
`wc -l`, `awk` y `head` sobre ficheros temporales fuera del repositorio
(`/tmp`), nunca cargando los CSV completos en el contexto de esta sesión.

## Relevante para tareas futuras

- Ambos recursos son completamente públicos y no dependen de ningún
  registro pendiente: la carga completa real no tiene ningún bloqueo de
  credenciales que resolver antes.
- El dataset tiene un desfase de publicación notable: a fecha de esta
  captura (2026-08-13) el recurso más reciente solo llega a junio de 2024.
  Una tarea futura que implemente el productor continuo real debería
  revisar primero si el Ayuntamiento ha publicado un recurso más reciente
  (vía `package_show` sobre el id `300321-0-aforos-peatones-bicicletas`),
  no asumir que los recursos usados aquí siguen siendo los últimos.
- El hallazgo de que este CSV está agrupado por estación (no por fecha, a
  diferencia del de `ruido_madrid.py`) es un precedente a tener en cuenta
  si una tarea futura captura otro recurso "histórico acumulado" de
  datos.madrid.es: conviene verificar el orden real de las filas (con
  `awk`/`head`/`tail`) antes de asumir que un patrón de "cortar al cambiar
  de fecha" funciona sin más.
- Igual que en las tareas 003-008 y 012, este productor sigue sin estar
  conectado a ningún destino de almacenamiento definitivo (S3/Bronze); eso
  llegará en una tarea posterior, tras aplicar la infraestructura de la
  tarea 001. `TODO(kafka)` queda marcado en el módulo por consistencia con
  el resto de productores de datos que cambian con el tiempo (no es una
  fuente de referencia como las tareas 009-011).
- El campo `mode` (`"peatones"`/`"bicicletas"`) junto con
  `pedestrian_count`/`bicycle_count` es el patrón elegido aquí para
  representar "dos redes de sensores distintas, un esquema común"; si una
  tarea futura tuviera que combinar fuentes con la misma naturaleza (varias
  redes de sensores midiendo magnitudes distintas en ubicaciones distintas),
  este es un precedente razonable a seguir en vez de forzar un cruce
  espacial/temporal que la fuente no soporta.
