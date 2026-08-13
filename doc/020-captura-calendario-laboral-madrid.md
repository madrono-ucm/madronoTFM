# 020 — Captura del calendario laboral y festivos de Madrid (muestra, carga puntual de referencia)

## Qué se implementó

`ingesta/capturas/calendario_laboral_madrid.py`: décimo productor de carga
puntual de referencia del proyecto (tras `callejero_madrid.py` tarea 009,
`barrios_distritos_madrid.py` tarea 010, `poi_madrid.py` tarea 011). Descarga
el calendario laboral oficial de Madrid (dataset `300082-0-calendario_laboral`
de datos.madrid.es) y lo normaliza a un registro por día natural, con su tipo
de jornada (laborable/festivo/sábado/domingo) y, en los días festivos, el
ámbito del festivo (nacional/regional/local) y su nombre. Sin bucle, sin
`--interval-seconds`, sin credenciales.

- `ingesta/capturas/samples/calendario_laboral_madrid_sample.json`: muestra
  real commiteada — los 365 días de 2026 (el año más reciente disponible en
  la fuente en el momento de esta captura), descargados en vivo ejecutando
  `python3 -m ingesta.capturas.calendario_laboral_madrid`.
- `ingesta/tests/test_calendario_laboral_madrid.py` +
  `ingesta/tests/fixtures/calendario_laboral_madrid_sample.csv`: tests sin
  red, usando un extracto de 9 filas reales del CSV completo.
- `ingesta/README.md`: nueva sección para esta fuente.

## Fuente elegida y por qué

Recurso **CSV** del dataset "Calendario laboral" (id
`300082-0-calendario_laboral`) de datos.madrid.es
(`.../resource/300082-1-calendario_laboral-csv/download/300082-1-calendario_laboral-csv.csv`),
accesible sin autenticación. Se descartó el ICS (también publicado por el
dataset): verificado en vivo que solo lista los días **festivos** de un
único año (14 eventos para 2025), sin el resto del calendario. El CSV, en
cambio, trae un registro por cada día natural desde el 01/01/2013 hasta el
31/12/2026 (5.112 filas, verificado en vivo) — el único recurso que cubre el
caso general (cualquier día, no solo festivos) que pedía la tarea.

## Dos problemas de calidad de datos de la propia fuente, documentados y no corregidos

Detectados recorriendo las 5.112 filas reales: (1) falta el 29/02/2016 —
2016 fue bisiesto pero el CSV salta del 28/02 al 01/03, el único hueco de
toda la serie — no se rellena con un valor inventado; (2) dos días marcados
`festivo` con `Tipo de Festivo` vacío en la fuente (15/05/2016 y
02/05/2023) — `normalize_day_record` deja `holiday_type`/`holiday_type_raw`
a `None` en vez de inferir un valor. Ambos casos están cubiertos por tests
usando las filas reales correspondientes, no fabricadas.

## Decisiones de diseño

- **Esquema con `day_type` (raw de la fuente) + `is_holiday` (derivado)**:
  `is_holiday = (day_type == "festivo")` es el campo pensado directamente
  para el caso de uso que motiva la tarea — que el modelo de afluencia trate
  un festivo entre semana como un domingo sin tener que interpretar
  `day_type` cada vez.
- **`holiday_type` normalizado a nacional/regional/local + `holiday_type_raw`
  con el texto original**: la fuente usa 4 valores no vacíos en `Tipo de
  Festivo` (`"Festivo nacional"`, `"Festivo de la Comunidad de Madrid"`,
  `"Traslado de la fiesta de la Comunidad de Madrid"`,
  `"Festivo local de la ciudad de Madrid"`); se mapean a los tres ámbitos
  pedidos por el enunciado vía `HOLIDAY_TYPE_MAP`, conservando el texto
  original para no perder la distinción entre un traslado y el festivo
  regional que traslada.
- **Muestra = un único año completo (2026), no el histórico 2013-2026
  completo**: el dataset entero no es grande (~150 KB, 5.112 filas), pero se
  prefirió commitear solo un año — ya demuestra el esquema completo (los
  tres ámbitos de festivo aparecen en 2026) y es más legible como fixture
  que un JSON de 5.112 registros. `select_year(records, year=None)` por
  defecto toma el año más reciente presente en el CSV descargado (no un año
  fijo hardcodeado), para que la muestra siga siendo "el año más relevante"
  aunque esta captura se reejecute en el futuro.
- **Se descarga el CSV completo siempre** (no hay forma de filtrar por año
  en origen) y se normaliza entero antes de recortar a un año: el coste es
  trivial (~150 KB, sin paginación) y evita depender de asunciones sobre qué
  año pedir antes de conocer el contenido real del CSV.

## Captura real en vivo

Se completó una **captura real en vivo**: la muestra commiteada son los 365
días reales de 2026 descargados ejecutando el módulo tal cual contra el CSV
público de datos.madrid.es durante esta sesión — no son datos de ejemplo
generados a mano. No hubo ningún bloqueo de acceso que documentar (a
diferencia de las tareas 003, 012, 018 y 019).

## Tests

`ingesta/tests/test_calendario_laboral_madrid.py`: no dependen de la red,
usan `ingesta/tests/fixtures/calendario_laboral_madrid_sample.csv` (9 filas
reales extraídas del CSV completo descargado en vivo, elegidas para cubrir
laborable/sábado/domingo, los tres ámbitos de festivo, un traslado regional
sin nombre, y los dos casos reales de `Tipo de Festivo` vacío). Cubren
`parse_csv_rows`, `normalize_day_record` y `select_year` (filtro explícito y
por defecto al año más reciente), más una verificación de esquema sobre la
propia muestra commiteada (365 días, un único año, 14 festivos reales de
2026 con los tres ámbitos representados). Suite completa del proyecto
verificada tras el cambio: **165 tests** (154 previos + 11 nuevos), todos en
verde.

## Relevante para tareas futuras

- El campo `is_holiday` de este módulo es la pieza que le faltaba al
  proyecto para que el modelo de afluencia pueda tratar un festivo entre
  semana como fin de semana: una futura tarea de transformación Silver/Gold
  que cruce afluencia con calendario debería usar `is_holiday` (o
  `day_type`) directamente en vez de mantener su propia lista de festivos.
- `holiday_type_raw` conserva el texto original de la fuente (incluida la
  distinción entre un festivo regional y su traslado) por si una tarea
  futura necesita esa granularidad; `holiday_type` ya trae la normalización
  nacional/regional/local pedida por el enunciado para el caso general.
- Los dos problemas de calidad de datos documentados (día 29/02/2016
  ausente, dos festivos sin `Tipo de Festivo`) son de la fuente, no de este
  módulo: si una tarea futura vuelve a descargar el CSV completo y encuentra
  que el Ayuntamiento los ha corregido, no hace falta ningún cambio de
  código — el módulo ya maneja ambos casos (hueco de fecha, tipo vacío) sin
  asumir que están siempre presentes.
- `TODO(kafka)` queda marcado en el módulo por consistencia con el resto de
  productores, aunque no se espera que esta fuente de referencia conecte
  nunca a un broker Kafka (mismo razonamiento que en las tareas 009-011).
