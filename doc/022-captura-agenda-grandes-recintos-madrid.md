# 022 — Captura de la agenda de grandes recintos de Madrid (deporte, conciertos, ferias; muestra)

## Qué se implementó

`ingesta/capturas/agenda_recintos_madrid.py`: productor de la agenda de
próximos eventos de los grandes recintos de Madrid (deporte, conciertos,
ferias) que generan picos de afluencia conocidos con antelación. Dos modos,
mismo patrón que `bluesky_menciones_madrid.py` (tarea 016):

- `fetch_venue_agenda(venue_id, ...)`: agenda de un recinto concreto —
  modo bajo demanda.
- `sweep_all_venues(...)`: agenda de todos los recintos cubiertos — modo
  barrido programado.

Documentación completa (esquema, hallazgos, decisiones) en
`ingesta/README.md`, sección `capturas/agenda_recintos_madrid.py`.

## Decisión central: reutilizar la agenda de esMadrid, no scrapear cada recinto

Antes de escribir un scraper por recinto se investigó, para cada uno de los
7 recintos del enunciado, si existía una fuente estructurada propia. El
hallazgo principal es que **la agenda de esMadrid, ya capturada en
`agenda_eventos_madrid.py` (tarea 017), incluye eventos reales de 6 de los
7 recintos objetivo**, identificados por su propio campo `nombrert`
(verificado en vivo descargando el feed completo, ~4,4 MB, 1.050 eventos):
12 partidos en el Bernabéu, 15 en el Metropolitano, 89 conciertos/eventos
en Movistar Arena, 52 ferias en IFEMA, 2 jornadas en el Hipódromo de la
Zarzuela, 4 eventos en Caja Mágica. Por eso este módulo **no hace ninguna
petición HTTP nueva**: filtra por nombre de recinto el mismo feed XML que
ya descarga `agenda_eventos_madrid.fetch_esmadrid_services_raw`, y
reutiliza `normalize_esmadrid_event` para el parseo. Es la fuente más
estructurada, estable y ya verificada disponible — reutilizarla evita
mantener un scraper HTML frágil por cada sitio web de cada recinto.

## Corrección importante sobre la lista de recintos: solo 6 recintos físicos, no 7

Se investigó en vivo y se confirmó que **"WiZink Center" y "Movistar
Arena" son el mismo recinto físico** (Palacio de Deportes de la Comunidad
de Madrid, Av. de Felipe II): cambió de nombre comercial el 1 de enero de
2025, no son dos recintos distintos. El "Palacio de Vistalegre" que el
enunciado asocia entre paréntesis a Movistar Arena ("antiguo Palacio de
Vistalegre") es en realidad un edificio distinto, en Carabanchel — la
propia agenda de esMadrid tiene una entrada separada para él
(`"Palacio Vistalegre Arena"`, 20 eventos), no usada aquí porque no es uno
de los recintos que pedía el enunciado. Se implementa un único
`venue_id="movistar_arena"` que cubre lo que el enunciado listaba como
"WiZink Center" y "Movistar Arena" a la vez. Los dos estadios de fútbol
también cambiaron de nombre comercial por patrocinio (Cívitas Metropolitano
→ "Riyadh Air Metropolitano" en 2025); `VENUES` documenta ambos nombres.

`wizinkcenter.es` como dominio propio se investigó de forma independiente
(antes de descubrir el punto anterior) y resultó bloqueado por WAF a nivel
de dominio completo (`403` incluso en `/robots.txt`, con cualquier
User-Agent) — queda documentado en `UNAVAILABLE_VENUES`, aunque ya no hace
falta: el recinto real está cubierto como `movistar_arena`.

## Otras fuentes investigadas y descartadas (decisiones documentadas en detalle en el README)

- **IFEMA Madrid tiene su propia agenda con JSON-LD `schema.org/Event`**
  (43 eventos reales verificados en vivo) — descartada solo por
  simplicidad, a favor de un único mecanismo (esMadrid) para los 6
  recintos.
- **Calendario oficial de Real Madrid / Atlético de Madrid**: aplicaciones
  Angular pesadas sin datos en el HTML servido — scraping frágil de una
  API privada no documentada, descartado.
- **`fixturedownload.com`** (calendario LaLiga 2026/27 en JSON, incluye
  estadio): la fuente más rica encontrada para fútbol, pero **se descartó
  explícitamente** porque su `robots.txt` incluye
  `User-agent: ClaudeBot` / `Disallow: /` — un bloqueo dirigido
  específicamente a rastreadores de Claude, que se respeta aunque el
  acceso fuera técnicamente posible.
- **`openfootball/football.json`** (GitHub, dominio público): no incluye
  el estadio y, verificado en vivo, la temporada 2026-27 aún no estaba
  publicada en la fecha de esta captura.

## Aforo: campo presente pero siempre `null`

El enunciado pedía "aforo si el recinto lo publica". esMadrid no publica
aforo por evento, y las cifras "oficiales" de aforo investigadas en vivo
(en particular el nuevo Bernabéu tras su reforma: cifras contradictorias
de prensa entre 78.297 y 85.500, sin cifra oficial pública del club) no
son lo bastante fiables para incrustarlas como dato estático. Se prefirió
dejar `capacity` siempre a `null` antes que arriesgar un número
incorrecto.

## Hallazgo colateral y corrección en `agenda_eventos_madrid.py` (tarea 017)

Al inspeccionar eventos reales de fútbol se descubrió que algunas entradas
del feed de esMadrid traen el título con entidades HTML sin decodificar
dentro de su propio `CDATA` de origen (p.ej. `"Real Madrid - M&aacute;laga
CF"` en vez de `"Real Madrid - Málaga CF"`), a diferencia del resto del
feed que usa UTF-8 directo — un problema de calidad de datos de la fuente
en sí. `agenda_eventos_madrid.normalize_esmadrid_event` ya aplicaba
`html.unescape` a `description`/`schedule_text` pero no a `title`. Se
corrigió como parte de esta tarea (mismo criterio ya usado para los otros
campos), ya que `agenda_recintos_madrid.py` construye sus registros sobre
esa función. La muestra ya commiteada de la tarea 017
(`agenda_eventos_madrid_sample.json`) no tenía ningún título afectado, así
que no hizo falta regenerarla; sí se verificó que sus tests siguen en
verde tras el cambio.

## Captura real en vivo

Se completó una **captura real en vivo**: la muestra commiteada en
`ingesta/capturas/samples/agenda_recintos_madrid_sample.json` son 17
eventos reales (3 por recinto, 2 para el Hipódromo de la Zarzuela — todos
los disponibles) de los 6 recintos cubiertos, obtenidos ejecutando
`python3 -m ingesta.capturas.agenda_recintos_madrid` tal cual durante esta
sesión — no son datos de ejemplo generados a mano. Incluye partidos reales
de LALIGA en el Bernabéu y el Metropolitano, conciertos reales (Kanye West,
BTS en el Metropolitano; varios en Movistar Arena), ferias de IFEMA, la
temporada del Hipódromo de la Zarzuela y eventos de Caja Mágica.

## Tests

`ingesta/tests/test_agenda_recintos_madrid.py`: no dependen de la red,
usan el fixture `fixtures/agenda_recintos_madrid_sample.xml` (7 `<service>`
reales extraídos del feed completo descargado en vivo: uno por cada uno de
los 6 recintos cubiertos, más `"Teatro de la Zarzuela"` como señuelo para
comprobar que el filtro del Hipódromo de la Zarzuela —cuyo nombre en la
fuente lleva un espacio inicial— no lo confunde con otro recinto que
comparte la palabra "Zarzuela"). Cubren `_infer_event_type`,
`normalize_venue_event`, `fetch_venue_agenda` (filtrado, límite, recinto
desconocido, y el caso `wizink_center` → mensaje de error redirigiendo a
`movistar_arena`) y una verificación de esquema sobre la propia muestra
commiteada. Suite completa del proyecto verificada tras el cambio: **199
tests** (182 previos + 17 nuevos), todos en verde.

## Relevante para tareas futuras

- Este es el primer caso del proyecto en el que una tarea nueva **no añade
  ningún acceso de red nuevo**, sino que reutiliza por completo una fuente
  ya integrada (filtrando por un campo que ya traía). Si una tarea futura
  necesita datos de otro recinto/entidad de Madrid, vale la pena
  comprobar primero si `agenda_eventos_madrid.py` (esMadrid o el dataset
  municipal) ya lo cubre antes de escribir un scraper nuevo — el hallazgo
  de esta tarea es que esa agenda es sorprendentemente amplia (1.050
  eventos, muchos recintos privados incluidos).
- El bloqueo de `fixturedownload.com` por su `robots.txt` dirigido
  específicamente a `ClaudeBot` es el primer caso del proyecto de una
  fuente descartada explícitamente por esta razón (no por WAF, no por
  necesitar registro): si una tarea futura encuentra un sitio con buenos
  datos abiertos pero con esta señal en su `robots.txt`, debería aplicar
  el mismo criterio y no usarlo, aunque el acceso HTTP funcione.
- Si en el futuro cambia otra vez el patrocinador de alguno de los
  estadios (Bernabéu, Metropolitano) o de Movistar Arena, `VENUES` deja de
  hacer *match* con el feed de esMadrid hasta que se actualice
  `esmadrid_names` a mano — es un riesgo conocido y documentado en el
  propio módulo, no un bug.
- `openfootball/football.json` no tenía publicada la temporada 2026-27 en
  la fecha de esta captura (mediados de agosto de 2026, justo cuando
  arranca la temporada); si una tarea futura la necesita para algo más
  amplio que el estadio (p.ej. calendario completo de LaLiga), conviene
  comprobar de nuevo si ya está disponible antes de asumir que sigue sin
  publicarse.
- IFEMA Madrid tiene su propia agenda con JSON-LD `schema.org/Event` en
  `https://www.ifema.es/calendario` (43 eventos reales verificados en
  vivo), no usada aquí por simplicidad (ver arriba). Queda anotada por si
  una tarea futura prefiere esa fuente directa para IFEMA en concreto —
  es más rica que lo que trae esMadrid para ese recinto.
- `TODO(kafka)` queda marcado en el módulo por consistencia con el resto
  de productores de muestra, aunque no se despliega ningún scheduling en
  esta tarea.
