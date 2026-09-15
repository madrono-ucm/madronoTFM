---
kind: vic-eval
title: "Memoria — §6.7–6.8 Explotación y ética: re-verificación profunda tras FIL_69-99 (PRIORIDAD 2) + diagrama de secuencia de una consulta"
owner: Claude (Memoria)
status: pending
created_at: "2026-09-15"
depends_on: []
---

## Contexto

**Esta es la sección con más churn de todo el documento.** `VIC_38`
(10/9) dejó §6.7 con 19 tools agrupadas en 3 familias y 3 superficies de
explotación (asistente, mapa animado, explorador). Desde entonces han
aterrizado ~30 tickets (`FIL_69`-`99`) que tocan exactamente esta capa:
traza de herramientas por turno + catálogo "¿qué puedo preguntar?"
(`FIL_95`), showcase de las "6 capas" (`FIL_95`-`99`, incluye "ficha de
modelo" `FIL_97` y "explica esta respuesta" `FIL_99`), pases de UX en el
mapa y el explorador (lenguaje llano, menos jerga), cambios del modelo de
chat (osciló entre `qwen3.8-27b` y `llama-3.3-70b-versatile` varias veces
— la memoria ya evita nombrar un modelo concreto, mantener esa decisión),
observabilidad MCP (`FIL_73`), y endurecimiento de `consulta_grafo`
(`FIL_72`). Es muy probable que el recuento de 19 tools, la descripción
del chat y la lista de "familias" ya no sea exacta.

## Alcance — el más profundo de toda la ronda

1. **Recontar tools desde cero**: `asistente/mcp_agent/server.py::TOOLS`
   (o `_TOOLS`, confirmar el nombre actual — el propio `asistente/
   README.md` menciona un generador `python -m asistente.gen_tabla_tools`,
   `FIL_93` — usarlo si existe para no transcribir a mano). Si el número
   subió más allá de 19, reescribir el párrafo de familias de `VIC_38`
   con las tools nuevas categorizadas correctamente.
2. **La aplicación web**: releer el estado real tras `FIL_69`-`75`/`95`-`99`
   — landing, auth, chat. ¿Sigue siendo "autenticación de demostración"?
   ¿El chat ahora muestra una traza de qué herramientas invocó (`FIL_95`)
   y un catálogo de preguntas sugeridas? Esto es una mejora real de
   explicabilidad que merece una frase en la memoria si no está ya.
3. **El explorador del grafo en vivo**: `VIC_38` lo describió en una
   frase corta. Tras `FIL_67` Parte 3, `FIL_68` (chatbot incrustado),
   `FIL_69` (recorrido guiado/storytelling), `FIL_74` (enlace público +
   redeploy), y el pase de UX de `FIL_69`-hoy — probablemente merece un
   párrafo propio más rico, no solo una frase de contraste con el mapa
   animado.
4. **El "showcase" (`FIL_95`-`99`)**: leer `tasks/FIL_95`-`99` y el plan
   `7f2690c` ("plan de showcase FIL_95-99, hacer visibles y brillar las 6
   capas") para entender qué son exactamente esas "6 capas" y si merecen
   nombrarse explícitamente en la memoria como la síntesis final de la
   capa de explotación — es probable que esta sea la mejor manera de
   cerrar §6.7 con una visión de conjunto.
5. **§6.8 Ética/legal**: confirmar que sigue vigente sin cambios (afluencia
   derivada en vez de Google Maps, RGPD) — riesgo bajo aquí.
6. **Diagrama**: un diagrama de **secuencia** (no de arquitectura) de una
   consulta real de extremo a extremo: usuario → chat web (o explorador) →
   LLM decide tool(s) → agente MCP → Athena/Neo4j/modelo ONNX → respuesta
   con veredicto+fiabilidad+explicación. Este diagrama es distinto del de
   `VIC_47` (arquitectura estática) — ilustra el *flujo de una interacción*,
   más parecido a un diagrama de secuencia UML simplificado. Usar
   `graphviz` (con `rankdir` apropiado) o considerar si un diagrama de
   secuencia real (actor/lifelines) se ve mejor hecho a mano con
   `matplotlib`/`patches` — decidir por legibilidad, no por preferencia
   técnica.

## Fuentes técnicas

`asistente/README.md`, `asistente/mcp_agent/server.py`, `tasks/FIL_67`
(Partes 1-3), `FIL_68`, `FIL_69`-`75`, `FIL_95`-`99`, `doc/README.md`
(bitácora) para contexto rápido de cada uno sin leer los ~30 tickets
palabra por palabra si el tiempo aprieta — priorizar los que tienen
"memoria"/"showcase"/"UX" en su título.

## Criterios de aceptación

- Recuento de tools verificado con la fuente de verdad del código
  (`gen_tabla_tools` si existe), no de memoria de sesiones anteriores.
- Las 3 (o más) superficies de explotación descritas con precisión y
  proporcionalmente a su importancia real hoy.
- Diagrama de secuencia de una consulta end-to-end insertado.
- Nada de lo escrito por `VIC_38` se pierde sin motivo — esta ronda
  **añade y corrige**, igual que hacían los tickets `VIKT_*`.
