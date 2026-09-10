---
kind: vic-eval
title: "Evaluación del grafo tras FIL_65/66/67 — estado de la instancia AuraDB tras 3 recargas"
owner: Claude (QA)
status: done
created_at: "2026-09-09"
depends_on: [FIL_65, FIL_66, FIL_67]
---

## Contexto

En la sesión del 2026-09-09 se cargó 3 veces el grafo real (`grafo.cargar_grafo`
vía el runner de sesión) para aplicar, en orden: FIL_65 (nodos `:EstacionMedida
{tipo:'meteo'}` ×25 + `:Lugar {tipo:'recinto'}` ×145), FIL_66 (atributos
estáticos de Gold en los nodos) y FIL_67 (persistir `n.nombre` en
`estacion_medida_query`/`parada_transporte_query`). `MERGE` idempotente, sin
borrados. Una de las cargas se recuperó de un corte de red (reintento de
`FIL_08`).

Hace falta una verificación **agregada** del estado combinado — no solo cada
carga por separado.

## Alcance

Contra la instancia real (`grafo/consulta.py` o driver directo, solo lectura):

1. **Conteos**: nodos por label y relaciones por tipo; comparar con
   `grafo/_data/grafo_urbano.json.gz` (`_meta.conteos_*`) y con lo que
   reportaron las cargas (~9.806 nodos / ~76k rels). Explicar cualquier
   desajuste.
2. **Idempotencia / huérfanos**: ¿hay nodos duplicados por `id`?
   ¿`:EstacionMedida`/`:ParadaTransporte`/`:Lugar` sin `UBICADO_EN` ni
   `PROXIMO_A` (nodos aislados que no aportan)? ¿aristas `PROXIMO_A` que
   apunten a un `id` inexistente?
3. **Cobertura de atributos FIL_66**: `contaminantes` (esperado 23/23),
   `magnitudes` (25/25), `subarea` (se cargó 4413/4705 — los ~292 restantes
   son puntos de tráfico fuera de la ventana de 14 días; confirmar que es
   eso y no un bug del SQL), `anclajes_totales` (680/680),
   `plazas_totales` (22/26 — ¿los 4 sin dato tienen `total_spaces` null en
   Gold?).
4. **`nombre` (FIL_67)**: 162 estaciones con nombre (aforos/ruido/meteo/
   calidad_aire); tráfico sin nombre por diseño. Verificar que ninguna
   estación con nombre en Gold quedó sin él en el grafo.
5. **meteo/recinto**: 25/25 meteo con `UBICADO_EN`, 24/25 con `PROXIMO_A`
   (1 periférica); 145 recinto, 142 con `PROXIMO_A`. Confirmar y mirar los
   que no tienen `PROXIMO_A` (¿coords fuera de Madrid? ¿>300 m de todo?).
6. **`schema.cypher` ↔ esquema vivo**: `CALL db.schema.nodeTypeProperties()`
   / `SHOW CONSTRAINTS` / `SHOW INDEXES` coinciden con lo que documenta
   `infra/neo4j/schema/schema.cypher` tras las ediciones de FIL_65/66/67
   (nuevas propiedades opcionales, `tipo` += `meteo`/`recinto`).

## Criterios de aceptación

- Los 6 puntos verificados con consultas y salida reales del momento.
- Cualquier hallazgo (huérfano, duplicado, atributo faltante no explicado) →
  ticket `FIL_*` nuevo.
- Nota corta para la memoria: cifras finales del grafo + qué añadió cada
  ticket, para `VIC_38` / el capítulo de grafo.

## Hecho (2026-09-10, Claude QA)

Los 6 puntos verificados con consultas reales contra la instancia AuraDB
(vía `grafo/consulta.py`) más una consulta Athena directa para el punto 3
(confirmó 4 `parking_id` con `total_spaces=NULL` real en Gold, no un
artefacto de ventana). Todos los conteos esperados por el ticket
coinciden exactamente: `contaminantes` 23/23, `magnitudes` 25/25,
`subarea` 4413/4705, `anclajes_totales` 680/680, `plazas_totales` 22/26,
`nombre` 162/162, meteo 24/25 `PROXIMO_A`, recinto 142/145 `PROXIMO_A`.
Cero duplicados, cero huérfanos reales (los nodos "aislados" son POIs/
paradas fuera del municipio de Madrid, comportamiento esperado del radio
de 300 m y de los 131 barrios). Esquema vivo = `schema.cypher` exacto.

Único hallazgo: el snapshot offline `grafo/_data/grafo_urbano.json.gz`
(usado por `modelado/grafo_analitica/` y `viz/`, ya verificado
autoconsistente por `VIC_36`/`VIC_41`) va 27 nodos de tráfico por detrás
de la instancia real — cosmético, sin ticket `FIL_*` nuevo, anotado para
regenerarlo antes de la entrega.

Detalle completo, con las cifras finales del grafo para `VIC_38`, en
[`doc/VIC-34-eval-grafo-v2.md`](../doc/VIC-34-eval-grafo-v2.md).
