# 007 — Captura de datos de ruido de Madrid (muestra)

## Qué se implementó

Sexto productor de datos de la Fase 1 (Ingesta), con el mismo alcance
reducido que las tareas 003/004/005/006 (captura puntual de muestra, no
productor continuo — la infraestructura AWS de la tarea 001 sigue sin
aplicarse):

- `ingesta/capturas/ruido_madrid.py`: descarga los valores diarios de
  contaminación acústica de la Red Fija del SIVCA (Sistema Integral de
  Vigilancia de la Contaminación Acústica) del Ayuntamiento de Madrid y, para
  poder resolver nombre/ubicación de cada estación, su catálogo de
  estaciones, los normaliza a un esquema mínimo, y guarda una **muestra
  pequeña** (5 estaciones por defecto, configurable, con hasta 4 registros
  cada una — uno por periodo D/E/N/T) en un fichero fijo — sin bucle, sin
  `--interval-seconds`, sin escribir en la capa Bronze particionada.
- `ingesta/capturas/samples/ruido_madrid_sample.json`: la muestra pequeña
  commiteada como fixture (20 registros: estaciones RF-01 a RF-05, 4
  periodos cada una).
- `ingesta/tests/test_ruido_madrid.py` +
  `ingesta/tests/fixtures/ruido_diario_sample.csv` +
  `ingesta/tests/fixtures/ruido_estaciones_sample.csv`: tests con
  `unittest` (sin red) que verifican el parseo del catálogo, el filtrado al
  último día presente en el CSV histórico, la normalización (incluida una
  estación sin metadatos conocidos en el catálogo), y que la muestra
  commiteada cumple el esquema esperado.
- `ingesta/README.md`: nueva sección para esta fuente (fuente elegida,
  formato real encontrado, variables de entorno, esquema, y la nota sobre el
  acceso en vivo desde este entorno).

## Fuente elegida y por qué: agregado diario, no tiempo real

Se investigaron los datasets de ruido de datos.madrid.es. A diferencia de
calidad del aire (tarea 006), **no existe un dataset de ruido con
granularidad horaria/tiempo real** en el portal: la Red Fija del SIVCA solo
publica un agregado **diario** por estación y periodo horario. Se eligió el
dataset "Contaminación acústica. Datos diarios" (id
`215885-0-contaminacion-ruido`) por ser el más granular y actualizado
disponible para esta red (actualización diaria excepto fines de semana y
festivos); el resto de datasets de ruido del portal (histórico mensual,
mapas estratégicos de ruido) son agregados a un plazo aún mayor. Sigue
encajando con el objetivo de la tarea ("datos.madrid.es publica niveles
sonoros por estación").

El recurso es un único CSV con el **histórico completo desde 2014**
(~540.000 filas, ~24 MB a fecha de esta captura), publicado en ISO-8859-1
(Latin-1) con coma decimal — a diferencia del JSON/CSV UTF-8 de calidad del
aire. No hay un recurso separado por día, así que `parse_latest_day_entries`
recorre el fichero completo pero solo conserva en memoria las filas del
último día presente (el fichero está ordenado cronológicamente ascendente),
en vez de acumular todo el histórico.

El CSV diario no incluye nombre, dirección ni coordenadas de la estación
(solo un código numérico plano), así que este productor combina una segunda
fuente: el dataset "Estaciones de medición de ruido de la Red Fija del
SIVCA" (id `211346-0-estaciones-acusticas`), con esos metadatos (código
`RF-01`, `RF-02`...) — mismo patrón de dos fuentes combinadas que
`calidad_aire_madrid.py` (tarea 006), `aparcamientos_madrid.py` (tarea 005)
y `bicimad.py` (tarea 004). Ese catálogo publica latitud/longitud con un
formato peculiar (`"-3.691.877"` en vez de `-3.691877`, puntos de más por un
error de exportación con separador de miles); `_parse_grouped_decimal`
corrige el formato tomando el primer fragmento como parte entera y
concatenando el resto como parte decimal.

Se verificó en vivo desde este entorno que ambos recursos (CSV diario y
catálogo de estaciones) son accesibles **sin ninguna autenticación ni API
key**.

## Captura real en vivo

Se completó una **captura real en vivo**: el fixture commiteado
(`ingesta/capturas/samples/ruido_madrid_sample.json`) son 20 lecturas reales
de las estaciones RF-01 (Paseo de Recoletos) a RF-05 (Barrio del Pilar), con
sus 4 periodos horarios cada una (diurno, vespertino, nocturno, total),
descargadas ejecutando `python3 -m ingesta.capturas.ruido_madrid` tal cual
contra ambos recursos públicos durante esta sesión — no son datos de
ejemplo generados a mano. El último día disponible en el momento de la
captura fue 2026-08-10 (el dataset se actualiza con un día de retraso,
"disponible a lo largo del día siguiente a su finalización", y no publica
datos de fin de semana/festivos), con 31 estaciones activas y 124 filas
(31 estaciones × 4 periodos) ese día.

## Decisiones de diseño (por qué)

- **Muestra medida en estaciones, no en registros**: a diferencia de las
  tareas 003-006 (donde `..._SAMPLE_SIZE` cuenta registros de salida), aquí
  `MADRID_NOISE_SAMPLE_STATIONS` (5 por defecto) cuenta estaciones; cada
  estación aporta hasta 4 registros (uno por periodo D/E/N/T) del último
  día. Se decidió así porque el propio objetivo de la tarea pide
  explícitamente "unas pocas estaciones", y cada periodo de una misma
  estación aporta un valor de ruido genuinamente distinto (el nivel diurno y
  el nocturno de un mismo punto no son intercambiables) — recortar a "N
  registros" con el criterio de las tareas anteriores habría cortado a
  media estación en muchos casos.
- **CSV completo descargado pero solo el último día conservado en memoria**:
  la fuente no ofrece un recurso "solo el día más reciente", así que la
  descarga completa (~24 MB) es inevitable con esta API; `parse_latest_day_entries`
  evita al menos acumular las ~540.000 filas de histórico como objetos
  Python, quedándose solo con el último grupo de fecha visto al recorrer el
  fichero. Una tarea futura que capturase esta fuente de forma recurrente
  debería revisar si hay una forma de pedir solo el incremento diario (no
  se encontró ninguna en este dataset).
- **`measured_date` en vez de `measured_at`**: todos los productores
  anteriores usan `measured_at` (un instante con hora) porque sus fuentes
  son de tiempo real o casi. Esta fuente es un agregado diario sin hora
  asociada, así que se prefirió un nombre de campo distinto y honesto con
  esa granularidad en vez de forzar una medianoche u otra hora arbitraria
  bajo el nombre `measured_at`.
- **Estación desconocida en el catálogo → metadatos a `null`, no se
  descarta el registro**: mismo criterio que en tráfico (tarea 002),
  BiciMAD (tarea 004), aparcamientos (tarea 005) y calidad del aire (tarea
  006) — la captura debe reflejar la fuente tal cual, no solo el
  subconjunto con metadatos completos.
- **Sin `BronzeWriter` ni modo `--interval-seconds`**, igual que en las
  tareas 003-006 y por la misma razón: la tarea prohibía dejar algo
  programado o escribir sin acotar en el disco de la EC2.
- **Sin variables de entorno de credenciales**: ambos recursos de
  datos.madrid.es usados son públicos y no las necesitan, igual que BiciMAD,
  aparcamientos y calidad del aire.

## Relevante para tareas futuras

- Ambos recursos (CSV diario y catálogo de estaciones) son completamente
  públicos y no dependen de ningún registro pendiente: el día que se
  implemente un productor continuo real para esta fuente, no hay ningún
  bloqueo de credenciales que resolver antes.
- Si se implementa un productor continuo, el mayor punto a revisar es que
  la única fuente disponible es el CSV con el histórico completo (crece cada
  día hábil, ~24 MB y subiendo): descargarlo entero en cada ciclo no escala
  bien a largo plazo; conviene investigar si existe una forma de pedir solo
  el incremento (no se encontró en esta tarea) o cachear el histórico ya
  descargado y solo verificar/añadir el último día.
- No existe un dataset de ruido en tiempo real/horario en datos.madrid.es
  (a diferencia de calidad del aire, tarea 006): la granularidad más fina
  disponible para la Red Fija del SIVCA es diaria. Si en el futuro apareciera
  un dataset de mayor granularidad, valdría la pena reevaluar esta elección.
- Igual que en las tareas 003-006, este productor sigue sin estar conectado
  a ningún destino de almacenamiento definitivo (S3/Bronze); eso llegará en
  una tarea posterior, tras aplicar la infraestructura de la tarea 001.
- `TODO(kafka)` queda marcado en el módulo para cuando exista un broker
  Kafka desplegado, igual que en los productores anteriores.
- El campo `measured_date` (solo fecha, sin hora) rompe la convención
  `measured_at` que usan el resto de capturas de este proyecto; cualquier
  tarea de Silver/Gold que unifique el esquema de todas las fuentes de
  ruido/calidad del aire/tráfico deberá tener en cuenta esta diferencia de
  granularidad temporal real entre fuentes, no solo de nombre de campo.
