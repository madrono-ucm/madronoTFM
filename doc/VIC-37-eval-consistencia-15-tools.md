# VIC_37 — Consistencia documental tras 14→19 tools MCP (2026-09-10)

El ticket se abrió tras `FIL_67` (14→15, `consulta_grafo`), pero para
cuando se ejecuta ya habían aterrizado también `FIL_79`-`FIL_82` (15→19:
`calidad_aire_episodio`, `calidad_aire_cams`, `meteo_cercana`,
`avisos_meteo`). El barrido se hizo contra el estado real de hoy — 19
tools, no 15 — para no dejar el mismo trabajo a medias otra vez.

## Metodología

`grep -rn` de patrones de conteo obsoleto (`"14 tool"`, `"15 tool"`,
`"9 tools"`, `"las 14"`, etc.) en todo el repo, filtrando a mano los falsos
positivos ("las 14 funciones Lambda de productores" es un `14` totalmente
distinto, de `ingesta/`, no del asistente) y los registros históricos
(`tasks/FIL_NN_*.md`/`doc/NNN-*.md` ya cerrados describen el estado *de su
momento*, no se reescriben). Solo se corrigieron documentos que describen
el **estado actual** del sistema.

## 1. Recuento "N tools" — ⚠️ 4 sitios corregidos, 1 encontrado y no corregido (fuera de alcance)

- `asistente/mcp_agent/server.py`: ya decía "19 tools" en dos sitios
  (descripción del `MCPServer` y comentario de `_ANOTACIONES_LECTURA`) —
  correcto de antes. `_TOOLS` tiene exactamente 19 entradas, verificado
  contando la tupla real.
- **Corregido**: `README.md` (raíz) — el diagrama mermaid decía "10 tools"
  (línea 45, un tercer número obsoleto más aún que 14/15), y dos frases
  decían "las 14 tools" (líneas 137, 190). Las tres, a 19.
- **Corregido**: `asistente/chat.py` — docstring del módulo y un comentario
  decían "las 14"/"las 15 tools MCP" respectivamente. A 19 (el conteo
  total de tools MCP registradas; `_TOOLS_CHAT`, el subconjunto que de
  verdad expone el chat, sigue siendo un subconjunto deliberadamente más
  pequeño — no confundir ambos números).
- **Corregido**: `asistente/README.md` — la cabecera de la sección decía
  literalmente **"7 `tools`"** (dos veces) y más abajo "Las siete están
  montadas..." con una lista de endpoints HTTP incompleta (11 de 19). Este
  documento estaba mucho más atrasado de lo que el ticket asumía (asumía
  un desfase 14→15, no 7→19). Corregido el recuento y completada la lista
  de los 19 `GET /...` reales (verificados uno a uno contra el decorador
  `@router.get(...)` de cada fichero en `asistente/routers/`, no solo por
  el nombre del fichero).
- **Encontrado, no corregido (fuera de alcance de este ticket)**:
  `asistente/README.md` líneas ~9-45 narran en detalle el origen histórico
  de las 7 tools originales (esqueleto tarea 044 + `trafico_cercano` +
  `calidad_aire_prevista`) pero no tienen ninguna narrativa equivalente
  para las 12 tools añadidas después (`FIL_13` en adelante) — la tabla
  "Las 19 `tools` del agente MCP" más abajo sí las cubre todas, de forma
  compacta. Reescribir esa narrativa introductoria para las 12 restantes es
  contenido nuevo, no una corrección de conteo — se deja como nota para
  quien toque `asistente/README.md` a fondo (no se abre `FIL_*` porque no
  es un bug, es deuda editorial de bajo riesgo).
- **Encontrado, no corregido (artefacto binario, no fuente)**:
  `notebooks/demo_madrono.ipynb`, celda de salida cacheada (no la fuente
  `notebooks/build_demo_notebook.py`, que no tiene ningún número
  hardcodeado), imprime "servidor MCP «madrono» — 10 tools" — salida
  real de una ejecución de cuando el servidor tenía 10. Arreglarlo exige
  re-ejecutar el notebook contra un servidor vivo (`python notebooks/
  build_demo_notebook.py` + ejecución real), fuera del alcance de una
  sesión de solo documentación — dejado para quien re-ejecute el notebook
  de todas formas antes de la entrega.

## 2. Tests que hardcodean la lista — ✅ ya al día

`test_mcp_tools.py::TOOL_FUNCTIONS` (19 entradas, incluye `consulta_grafo`)
y `test_mcp_transport.py::_ESPERADAS` + `test_list_tools_expone_las_19` ya
estaban correctos — no quedaba ningún `14` suelto en estos dos ficheros.
`python -m pytest asistente/tests/test_mcp_tools.py asistente/tests/
test_mcp_transport.py -q` → **38 passed, 57 subtests passed**.

## 3. Routers — ✅ correcto, documentación completada (ver punto 1)

`asistente/main.py` monta los 19 routers de `tool` (más `chat` y
`grafo_explorador`, que no son `tools` MCP). `GET /consulta-grafo` existe
(`asistente/routers/consulta_grafo.py`) y ya estaba descrito en la tabla de
`asistente/README.md`; lo que faltaba era en la lista de endpoints del
párrafo introductorio (corregido arriba).

## 4. `grafo/consulta.py` — ⚠️ no estaba documentado, corregido

No aparecía ni en `grafo/README.md` ni en `infra/OPERACION.md` pese a ser
una pieza real del directorio (`FIL_67`). Añadida una sección nueva en
`grafo/README.md` ("Consultar el grafo real desde la línea de comandos")
con los dos ejemplos de su propio docstring, y una línea en la sección
"Comandos de verificación útiles" de `infra/OPERACION.md`, junto al
equivalente ya existente para Athena.

## 5. `_INSTRUCCIONES`/descripción del `MCPServer` para el LLM cliente — ⚠️ corregido

La cadena `description` de `server.py` nombraba las otras 18 tools una por
una pero nunca mencionaba `consulta_grafo` — un cliente LLM leyendo solo
esa descripción no sabría que existe. Añadida una frase breve.

## Verificación

- `grep -rn` de los patrones del criterio de aceptación, filtrando el falso
  positivo de "14 funciones Lambda": 0 menciones obsoletas restantes en
  documentos que describen el estado actual (quedan, deliberadamente, en
  registros históricos de `tasks/`/`doc/` ya cerrados).
- `python3 -c "import ast; ..."` sobre los dos `.py` tocados: sintaxis OK.
- `pytest asistente/tests/test_mcp_tools.py asistente/tests/
  test_mcp_transport.py -q`: verde (38 passed, 57 subtests).

## Hallazgos que NO se convierten en `FIL_*`

Ninguno de los dos puntos "encontrados, no corregidos" de la sección 1 es
un bug de comportamiento — son deuda documental/de artefacto de bajo
riesgo, no ocultan ninguna capacidad rota. No se abre ticket nuevo.
