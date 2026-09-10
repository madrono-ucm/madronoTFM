---
kind: fil
title: "Ficha de datos (/datos): el lakehouse hecho visible — linaje, conteos reales, frescura y el «pipeline congelado»"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-09-10"
depends_on: [FIL_63, FIL_83, FIL_91]
milestone: "M7"
target: "2026-09-13"
---

## Motivación

Showcase, pieza 2 de 5 (plan «hacer brillar todas las capas», 2026-09-10).

La **ingeniería de datos** es la mitad del TFM y no tiene **ni un pixel**
de UI. Todo el trabajo de captura (docs `002`–`050`), Bronze→Silver→Gold
sin Spark, vistas Athena (FIL_83) y los «3 días curados / pipeline
congelado» (§7.4) vive solo en `doc/` y en la memoria. Un visitante del
enlace no puede ver que hay un lakehouse real detrás del chat.

## Alcance

### 1. Endpoint `GET /datos/resumen`

JSON servido por el backend (EC2), cacheado (TTL de FIL_83). Contenido,
todo **derivado de datos reales**, nada hardcodeado:

- Por tabla Gold relevante (`gold.trafico_por_punto_hora`,
  `gold.calidad_aire_*`, ruido, meteo, afluencia, aparcamiento, eventos):
  nº de filas, rango temporal cubierto (`min/max` de la partición de
  fecha/hora), nº de puntos/estaciones distintas, última fecha con datos.
- Las **fuentes** de cada dominio (informo.madrid.es, portal de datos
  abiertos de aire, AEMET, CAMS/Copernicus, agenda de eventos…) con su
  cadencia de captura nominal.
- Estado del pipeline: `congelado_desde`
  (`timeutils.PIPELINE_CONGELADO_DESDE`) y los **3 días curados**
  (`ruta_saludable.dias()` / la lista de §7.4), con una frase de por qué
  (metodología, no producción 24/7).
- Si Athena no responde: degradación elegante como el resto
  (`disponible:false` + `motivo`), la página lo dice, no rompe.

### 2. Página `/datos` (estática, servida como el mapa)

- Un **diagrama de linaje** legible (SVG inline o mermaid ya soportado):
  fuentes → Bronze (S3 crudo) → Silver (tipado, hora Madrid) → Gold
  (agregados por punto·hora) → vistas Athena → herramientas del asistente.
- Las cifras de `/datos/resumen` en una tabla por dominio (filas,
  cobertura temporal, nº de puntos, frescura).
- Un bloque **«una consulta de verdad»**: el SQL Athena de
  `gold.trafico_por_punto_hora` para un punto y día concretos (el de
  `doc/VIKT-06-recorrido-e2e.md`, punto 4398) y su salida real capturada,
  con nota de que es reproducible.
- El panel «pipeline congelado vs reanudado»: qué se ve en cada caso.
- Lenguaje llano, misma línea visual que la landing (FIL_92) y el mapa.

## Fuera de alcance

- Ejecutar Athena en vivo desde el navegador del visitante (lo sirve el
  backend, cacheado).
- Reactivar el pipeline / tocar Terraform / captura (§7.4 lo congela a
  propósito).
- Reproducir el detalle de cada productor Lambda — el diagrama enlaza a
  los `doc/0xx`.

## Verificación

- `GET /datos/resumen` devuelve conteos que **cuadran** con una consulta
  Athena manual a la misma tabla (±0), y el rango temporal contiene los 3
  días curados.
- Con Athena caída, `/datos/resumen` responde `disponible:false` + motivo
  y la página muestra el aviso, no un error.
- La página abre desde el enlace de demo, el diagrama se lee en móvil
  (~400 px), navegación por teclado con foco visible.
- Test: `TestClient` sobre `/datos/resumen` con Athena mockeada (éxito y
  fallo); jsdom para el render de la tabla desde un `resumen` de ejemplo.
- `pytest asistente/` verde.

## Prioridad y secuencia

**Media-alta.** Es sobre todo estático + un endpoint de agregación; el
riesgo es de datos (que los conteos cuadren), no de diseño. Después de
FIL_83 (caché/vistas Athena, en main). Puede ir en paralelo a FIL_97.
Estimación ~1 día. Objetivo **2026-09-13**. Alimenta la parada «Datos» de
FIL_98.
