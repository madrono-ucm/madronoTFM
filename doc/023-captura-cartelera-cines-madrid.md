# 023 — Captura de cartelera y horarios de cines de Madrid (muestra)

## Qué se implementó

`ingesta/capturas/cartelera_cines_madrid.py`: complementa a
`agenda_recintos_madrid.py` (tarea 022) — ir al cine es otro "plan
alternativo" que Madroño podría recomendar, pero a diferencia de un
partido en el Bernabéu no hay una API oficial de las grandes cadenas
(Cinesa, Yelmo). Dos funciones:

- `fetch_cinema_showtimes(cinema_id)`: cartelera completa (película +
  horario + versión de idioma) de un cine concreto — modo bajo demanda.
- `sweep_premieres()`: estrenos destacados de la semana en España — modo
  barrido ligero, pensado para una futura captura diaria.

Documentación completa (esquema, hallazgos, variables de entorno) en
`ingesta/README.md`, sección `capturas/cartelera_cines_madrid.py`.

## Investigación de la fuente: JSON-LD sí, pero no `ScreeningEvent`

Siguiendo la indicación explícita del enunciado, se investigó primero si
las páginas de cartelera exponen JSON-LD `schema.org/ScreeningEvent` antes
de asumir que hacía falta parsear HTML a mano:

- **`cinesa.es`**: bloqueado por Cloudflare a nivel de dominio completo
  (`403` con página de challenge incluso en `/robots.txt`, verificado en
  vivo con varios User-Agent) — mismo tipo de WAF ya documentado para
  `wizinkcenter.es` en la tarea 022.
- **`yelmocines.es`**: accesible, pero aplicación ASP.NET clásica sin URLs
  de cartelera adivinables ni JSON-LD; forzar su scraping habría exigido
  mapear a mano su navegación (selector de ciudad/cine) antes de poder
  extraer nada, con el riesgo de fragilidad que el enunciado pedía evitar.
- **SensaCine** (`sensacine.com`, del grupo Webedia/AlloCiné): agrega la
  cartelera de **todas** las cadenas de España —Cinesa y Yelmo incluidas—
  bajo una única web. Verificado en vivo: sí publica JSON-LD
  (`schema.org/MovieTheater` con nombre/dirección/aforo de salas, e
  `ItemList` con los enlaces a cada película), pero **no publica
  `ScreeningEvent`** en ningún bloque estructurado — los horarios
  concretos no están ahí.

Se encontró, en cambio, algo casi tan robusto: los horarios están en el
propio HTML servido por el servidor (sin necesidad de ejecutar
JavaScript; `curl` sin cabecera de navegador ya lo devuelve completo) como
**atributos `data-*` explícitos y tipados** en cada franja horaria
(`data-showtime-time` en ISO 8601, `data-showtime-id`, `data-experiences`
en JSON) — pensados por el propio sitio para que su JavaScript de reserva
los lea, no texto libre que haya que interpretar con heurísticas frágiles.
Por eso se eligió SensaCine como única fuente para ambas cadenas, en vez
de intentar un scraper HTML distinto y más frágil por cadena.

## Términos de uso: zona gris, mismo criterio que la tarea 012

Se leyeron en vivo los términos legales de SensaCine
(`sensacine.com/servicios/terminos/`): reservan la reproducción/
distribución del sitio y limitan su uso a "privado y personal",
prohibiendo cualquier fin comercial sin consentimiento escrito. Es el
mismo tipo de zona gris ya documentado en la tarea 012
(`afluencia_lugares_madrid.py`, apartado 6.8 de la memoria): se trata como
admisible para una muestra pequeña en el marco académico de este TFM, pero
explícitamente **no apto para escalar** a scraping masivo o cualquier uso
comercial sin revisar antes esos términos directamente con SensaCine. El
`robots.txt` del sitio no añade ninguna restricción relevante adicional
(solo excluye rutas de utilidades internas y algunos bots de IA por
nombre; ninguno coincide con este cliente) — a diferencia de la tarea 022
(`fixturedownload.com`), aquí no hay ninguna señal `Disallow: /` dirigida
específicamente a un User-Agent de Claude. El `User-Agent` de este módulo
se identifica honestamente como investigación académica con contacto
(mismo patrón que `bluesky_menciones_madrid.py`), sin suplantar un
navegador.

## Hallazgo de calidad de datos: un defecto real de la propia fuente

Inspeccionando en vivo el HTML real de Cinesa Proyecciones se descubrió
que **algunas versiones de idioma aparecen duplicadas byte a byte en el
HTML de origen** (el mismo bloque "En V.O.S.E." de una película, con el
mismo `data-showtime-id`, repetido dos veces seguidas) — un defecto de la
propia plantilla de SensaCine, no un error de parseo. `fetch_cinema_showtimes`
deduplica explícitamente por `data-showtime-id` para no producir horarios
repetidos en el esquema normalizado; el fixture de test reproduce a
propósito esta duplicación real para verificarlo.

## Captura real en vivo, ambas cadenas

Se completó una **captura real en vivo**, sin ningún bloqueo que forzara
usar datos de ejemplo: la muestra commiteada en
`ingesta/capturas/samples/cartelera_cines_madrid_sample.json` son 18
registros reales (6 horarios de Cinesa Proyecciones + 6 de Yelmo Cines
Ideal + 6 estrenos de la semana del 14 de agosto de 2026), obtenidos
ejecutando `python3 -m ingesta.capturas.cartelera_cines_madrid` tal cual
durante esta sesión.

## Decisiones de diseño

- **Un registro `CINEMAS` con 4 cines (2 por cadena)**, pero
  `DEFAULT_CINEMA_IDS` limitado a uno de cada una (`cinesa_proyecciones`,
  `yelmo_ideal`) para la muestra por defecto, tal como pedía el objetivo
  ("al menos un cine de cada cadena"); los otros dos (`cinesa_mendez_alvaro`,
  `yelmo_la_vaguada`) quedan verificados en vivo y disponibles para
  `fetch_cinema_showtimes` bajo demanda sin tener que ampliar el registro
  en una tarea futura.
- **Dependencia nueva: `beautifulsoup4`**. El HTML real de SensaCine no es
  trivial de parsear con expresiones regulares de forma fiable (bloques
  anidados, versiones de idioma repetidas); se añadió como dependencia
  ligera y estándar en vez de reinventar un parser HTML a mano.
- **`sweep_premieres` no filtra por Madrid**: SensaCine publica una única
  lista nacional de estrenos de la semana (verificado en vivo, no hay
  parámetro de ciudad en esa página en concreto, a diferencia de la
  búsqueda de cines). Documentado explícitamente para que no se asuma
  cobertura geográfica que la fuente no ofrece.
- **Esquema flexible en `experiences`** (lista cruda tal como la publica
  la fuente, p.ej. `Format.Projection.Digital`,
  `Localization.Version.Original`): se prefirió no normalizar a un enum
  cerrado porque no hay forma de conocer de antemano todos los valores
  posibles (3D, IMAX, salas VIP...) sin observarlos en más cines de los
  que cubre esta muestra.

## Tests

`ingesta/tests/test_cartelera_cines_madrid.py`: 21 tests, no dependen de
la red. Usan dos fixtures HTML reales recortados a mano
(`fixtures/sensacine_cine_showtimes_sample.html`,
`fixtures/sensacine_estrenos_sample.html`), con títulos, URLs, fechas/horas
ISO y `data-showtime-id` reales tal como los devolvió sensacine.com.
Cubren el parseo del JSON-LD `MovieTheater`, la deduplicación del defecto
real de horarios repetidos, el orden por fecha/hora, el parseo de
duración/género/fecha de estreno en español, los casos límite (cine
desconocido, tarjeta sin título) y una verificación de esquema sobre la
propia muestra commiteada (cobertura de ambas cadenas). Suite completa del
proyecto verificada tras el cambio: **220 tests** (199 previos + 21
nuevos), todos en verde.

## Relevante para tareas futuras

- Si una tarea futura necesita ampliar la cobertura de cines más allá de
  Madrid capital o de las 4 fichas ya registradas, basta con añadir
  entradas a `CINEMAS` con su `sensacine_id` (visible en la URL de la
  ficha del cine en sensacine.com) — no hace falta ningún cambio de
  parseo, ya que `fetch_cinema_showtimes` es genérico por cine.
- El defecto de datos duplicados en el HTML de origen (mismo
  `data-showtime-id` repetido) es de SensaCine, no de este módulo: si en
  una recaptura futura ya no aparece, no hace falta ningún cambio de
  código — la deduplicación es un no-op inofensivo cuando no hay
  duplicados.
- Antes de escalar esta fuente a un productor continuo real (más cines,
  cadencia diaria u horaria), conviene revisar los términos de uso de
  SensaCine directamente con ellos (ver "zona gris" arriba) — el patrón ya
  aplicado en la tarea 012 con Google/`populartimes` es el precedente a
  seguir: seguir usándola tal cual para una muestra académica es
  razonable, escalarla a producción sin permiso no lo es.
- `TODO(kafka)` queda marcado en el módulo por consistencia con el resto
  de productores de muestra, aunque no se despliega ningún scheduling en
  esta tarea.
