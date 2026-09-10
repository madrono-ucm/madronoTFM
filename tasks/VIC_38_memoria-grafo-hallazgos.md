---
kind: vic-eval
title: "Memoria — integrar los hallazgos de grafo (FIL_52/64/65/66/67) en §6 y §7"
owner: Víctor / Claude (QA)
status: done
created_at: "2026-09-09"
depends_on: [FIL_52, FIL_64, FIL_65, FIL_66, FIL_67, VIC_34, VIC_36]
---

## Hecho (2026-09-10, Claude)

Escrito directamente en `documents/Memoria_TFM FV.docx` con `python-docx`,
anclando cada edición por subcadena única (nunca por índice de párrafo
contado a mano — un error de desfase así ya causó ediciones en el sitio
equivocado en una sesión anterior). Antes de escribir se releyó el `.docx`
completo de cero: **el trabajo de la sesión anterior (ticket `VIKT_12`,
14 tools/app web/mapa/secretos) nunca había llegado a aplicarse de
verdad** — un `git reset --hard origin/main` externo se llevó por delante
ese commit local antes de que se hiciera `git push`. Se rehizo todo ese
contenido en la misma pasada, ya con las cifras reales de hoy (**19**
tools, no 14 — `FIL_79`-`83` aterrizaron entre medias).

**§6.6** (tras el párrafo de Athena/Neo4j): dos párrafos nuevos — el patrón
medallion→grafo («dónde y qué hay cerca» = nodos, «qué valor en el
tiempo» = Gold, «qué valor tendrá» = `modelado/`) con la explicación de
por qué `agenda_eventos`/`aforos`/`transporte_publico_emt` no aportan
nodos propios; y el inventario final verificado por `VIC_34` (9806 nodos,
5 labels, 76002 relaciones, 4 tipos).

**§6.7**: de 7 a 19 tools, reagrupadas en 3 familias (antes 4, ya no
distinguía previsión ONNX de previsión-grafo como familias separadas —
ahora conviven en "previsión y contraste"). Tres párrafos nuevos: la
aplicación web (`FIL_62`/`63`, con nota de que el LLM es Groq con
proveedor/modelo configurables — el modelo por defecto ha cambiado ya dos
veces desde que se desplegó, así que no se fija un nombre concreto en la
memoria), la visualización animada del grafo (`FIL_36`+), y una tercera
superficie no contemplada por `VIKT_12`: el explorador del grafo en vivo
(`FIL_67` Parte 3, consulta Neo4j en directo con el chat incrustado).

**§7.1**: segunda instancia de "7 tools" corregida a 19 (la primera vez
solo se había corregido la de §6.7, no esta).

**§7.3** (antes de §7.4): nueva subsección de analítica de grafo —
centralidad/comunidades (`FIL_52`/`VIC_41`: top-3 PageRank e
intermediación, 54 comunidades vs 131 barrios, NMI/ARI) y resiliencia
(`FIL_64`/`VIC_36`: 683 puntos de articulación, 39,6 %/89,1 % de
fragmentación dirigida/aleatoria) **con el matiz de `FIL_86`
incorporado en el propio texto** — el 39,6 % se presenta explícitamente
como cota optimista, no como cifra ajustada, porque `VIC_36` demostró que
el recálculo por lotes de la curva subestima el daño real. Insertada
también la Figura 2 (`grafo_resiliencia.png`, imagen real embebida con
`python-docx`, mismo patrón que la Figura 1 existente) y un párrafo sobre
la correlación STGNN↔grafo (ρ pasó de 0,34 no significativo a 0,64
significativo tras `FIL_66`, cifra verificada en el artefacto committeado
`modelado/evaluation/artifacts/grafo_stgnn_vs_conectividad.json`).

**§7.4**: ventana de entrenamiento fija por la congelación del 30/8
(ya no "hasta 4 semanas"); cron de reentrenamiento ya no descrito como
pendiente (`doc/105` lo da por instalado y verificado); tres bullets
nuevos — alertado parcial (`FIL_16`), autenticación de demostración de la
app web, y los atributos de `FIL_66` sobre la ventana congelada (con las
cifras reales de `VIC_34`: `contaminantes`/`magnitudes` completos,
`subarea` 4413/4705, no "salió fino" como asumía este ticket antes de
verificarse — corregido para no repetir una suposición no confirmada).

**§7.5**: dos líneas futuras obsoletas corregidas — el export de STGNN a
ONNX ya no "habilitaría" ninguna tool (las basadas en STGNN ya sirven
nativas); el hueco de `ML_01` (meteo/festivos) ya estaba cerrado desde el
29/8 y ha sido sustituido por la deuda real con 7.3 (las dos ablaciones
descartadas).

**Anexo C**: URLs de la app web y el mapa animado, más el comando para
regenerar la analítica de grafo.

Verificado tras guardar: el documento sigue abriendo con `python-docx`
(163 párrafos, 145+18 insertados), grep de "siete herramientas"/"7 tools"
sin resultados, grep de las cifras/términos nuevos con hits en las
secciones esperadas, y la imagen nueva confirmada como un `w:drawing`
real (no una coincidencia de subcadena en el XML de namespaces).

Commit `docs(memoria): VIC_38 - ...` en `main`, empujado a `origin`.

## Contexto

`infra/neo4j/README.md` justifica Neo4j por "consultas de proximidad y
conectividad que un modelo tabular expresa mal", pero la versión actual de
la memoria apenas explota esa idea. La sesión del 2026-09-09 produjo
material real para el capítulo de grafo:

- **FIL_52** centralidad + comunidades Louvain (grafo vs 21 distritos).
- **FIL_64** resiliencia: puntos de articulación / puentes / k-core / curva
  de robustez (ataque dirigido vs aleatorio). Con caveat de modelado.
- **FIL_65/66** el grafo pasó de índice espacial mínimo a incluir estaciones
  meteo, recintos de eventos y **atributos por entidad** (qué contaminantes
  mide cada estación de aire, capacidades, subárea, altitud).
- **FIL_67** marco conceptual: *grafo = "dónde y qué hay cerca" · Gold =
  "qué valor, en el tiempo" · ML = "qué valor tendrá"*; y `consulta_grafo`
  (15ª tool) como acceso flexible al grafo.

## Alcance — redacción de memoria (coordinar con VIKT_10 editorial)

1. **§6 (arquitectura/explotación del grafo)**: actualizar el inventario del
   grafo a las cifras finales (`VIC_34`): 5 labels, ~9.8k nodos, 4
   relaciones, atributos por nodo. Explicar el patrón medallion→grafo
   (entidades fijas geolocalizadas = nodos; series de medidas = Gold) y por
   qué `agenda_eventos`/`aforos`/`transporte_publico_emt` quedan como
   quedan.
2. **§7 (resultados)**: subsección de analítica de grafo con FIL_52 + FIL_64.
   Incluir la figura `grafo_resiliencia.png` y la tabla top de puntos de
   articulación / comunidades. Redactar el **caveat** (`k_max=2`, "un viaje
   por línea") de forma que no se lea como diagnóstico operativo real
   (texto propuesto en `VIC_36`).
3. **§7.4 (limitaciones)**: pipeline congelado desde 2026-08-30 → los
   atributos de FIL_66 se calculan sobre una ventana corta; `contaminantes`
   por estación es estable, pero `magnitudes` de meteo salió fino
   (`temperature_c`/`humidity_pct`) por la congelación.
4. **Cruce STGNN ↔ grafo**: FIL_52 ya reportaba Spearman(importancia de
   arista, grado `PROXIMO_A`); tras FIL_66 subió a ρ≈0,64 (p<0,01) al
   densificarse el grafo. Decidir si va en §7 como "el modelo redescubre la
   estructura del grafo".

## Criterios de aceptación

- Borrador de las subsecciones (§6 grafo, §7 analítica de grafo, nota §7.4)
  entregado y revisado con `VIKT_10`.
- Todas las cifras trazables a un artefacto commiteado o a una consulta
  reproducible (`grafo/consulta.py`).
- Sin afirmaciones que `VIC_34`/`VIC_36` no hayan validado.
