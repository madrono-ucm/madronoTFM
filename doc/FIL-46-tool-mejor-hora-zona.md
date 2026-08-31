# FIL-46 — `mejor_hora_zona`: la capa social del mapa, en lenguaje natural

`FIL_45` puso la capa social **en el mapa** (perfiles de sensibilidad,
bandas OMS/UE, «mejor hora hoy», dosis). Este ticket la pone **en el
asistente**: la 14.ª tool MCP responde la pregunta que motivó `FIL_45` —

> «Tengo asma, ¿cuándo puedo pasear hoy por Vallecas?»

— componiendo lo que ya había, sin infra ni modelo nuevo.

## Qué hace

`mejor_hora_zona(zona, perfil="general", momento=None) -> MejorHoraZona`

1. **Resuelve `zona` (texto libre) a uno de los 21 distritos.**
   `asistente/mejor_hora_zona.py::_resolver_zona`: nombre exacto
   normalizado, `id` de distrito (`"13"`, `1`), subcadena en ambos
   sentidos, y un diccionario corto de **alias coloquiales** donde el
   nombre oficial no es obvio o una palabra cubre dos distritos
   (`vallecas` → ambiguo entre *Puente de Vallecas* y *Villa de Vallecas*;
   `moncloa`/`aravaca` → *Moncloa - Aravaca*; `san blas`, `el pardo`,
   `cuatro caminos` → *Tetuán*, …). Ambigüedad o zona desconocida →
   degradación con la lista de los 21 distritos, nunca excepción.

2. **Barrido «mejor hora hoy» por distrito + perfil.** Para cada una de las
   24 h del día curado calcula la **exposición media de los nodos del
   distrito** (`Σ_señal peso · norm(exposición)` — tráfico previsto del
   STGNN de grafo + NO₂ + O₃ interpolados + ruido diario por distrito),
   con los mismos pesos de perfil que `ruta_saludable` (`FIL_37`, 9
   perfiles tras `FIL_45`). Devuelve:

   | campo | qué |
   |---|---|
   | `mejor_hora` / `peor_hora` | argmin / argmax de la serie |
   | `franja_inicio`..`franja_fin` | racha de horas consecutivas ≤ mín + 20 % del rango |
   | `reduccion_vs_peor_pct` | cuánto baja la exposición entre la peor hora y la mejor |
   | `serie_horaria` | 24 valores (0..~1, sin unidad — para comparar horas entre sí) |

## Cómo, sin nada nuevo

`asistente/mejor_hora_zona.py` es Python puro y **reutiliza
`asistente/ruta_saludable.py`** (`_cargar` / `_expo_nodo` / `_norm` sobre
`asistente/modelos/grafo_ruta.json`, vendorizado por
`viz/build_grafo_ruta.py`). Sin Neo4j, sin Athena, sin red. Mismo criterio
de autocontención que `asistente/athena.py` respecto a `grafo/`.

## Ejemplo verificado

`mejor_hora_zona("13", "asma_epoc")` (día `2026-08-26`):
- → distrito **Puente de Vallecas**, 67 nodos.
- mejor hora **06:00**, peor **18:00**, franja limpia **03:00–07:00**,
  **−62 %** de exposición ponderada entre la peor hora y la mejor.
- La forma de la curva la marca el **O₃** (contaminante regional, pico de
  tarde): madrugada limpia, mínimo al alba, subida hasta media tarde.

`mejor_hora_zona("Vallecas", …)` → `disponible=false`,
`motivo="«Vallecas» abarca varios distritos (Puente de Vallecas, Villa de
Vallecas); indica cuál"`.

## Qué NO hace — sigue siendo encuadre

Las **alertas anticipadas por distrito** de `FIL_46` (emitir un aviso
cuando la previsión cruza un umbral OMS/UE en las próximas N h) siguen sin
implementar: el asistente es petición-respuesta, sin estado ni
suscripción. Faltan un **canal de notificación** (push/correo/webhook) y
una **política de umbral por distrito** (qué banda dispara, con qué
antelación, con qué frecuencia máxima, quién la define). `mejor_hora_zona`
da la franja limpia bajo demanda; el salto a aviso proactivo necesita esas
dos piezas.

## Encuadre (heredado de `FIL_45`)

Agregado por zona, sin datos personales · describe la previsión de aire y
hora, no señala barrios · apoyo a la decisión, no consejo médico ·
demostración de metodología (§7.4): 3 días curados, `fiabilidad` topada en
BAJA.

`asistente/tests/test_mejor_hora_zona.py` (17). Suite `asistente/` → 162 en
verde; `test_mcp_tools.py` / `test_mcp_transport.py` a 14 tools.
