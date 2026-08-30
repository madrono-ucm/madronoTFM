# VIC-17 — Evaluación técnica ronda 2: modelado/ (STGNN export real + Tabla 3)

Ejecutado 30/8. Ningún cambio de código.

## 1. Export del STGNN desde el registry real (no solo sintético)

`FIL_20` verificó el export de forma sintética (un `STGNN` recién
inicializado en el propio test, nunca entrenado ni registrado). Esta
pasada entrena y registra un `@champion` real:

```bash
python -m modelado.training.train_stgnn --panel modelado/_data/panel_calidad_aire.parquet --nombre calidad_aire --mlflow tier2-vic17
```

Resultado real: `madrono-stgnn-calidad_aire` v1 registrado (early
stopping en la época 50, mejor val en la 30). Export desde el registry:

```bash
python -m modelado.export.to_onnx --stgnn --modelo madrono-stgnn-calidad_aire --panel modelado/_data/panel_calidad_aire.parquet --nombre stgnn_calidad_aire_vic17
```

**Resultado**: `.onnx` real de 246.988 bytes, 123 nodos / 1.258 aristas
(grafo k-NN de coordenadas, `knn=8`), **paridad `max|Δ|=3.58e-07`** — muy
por debajo de la tolerancia (`1e-4`). Confirma `FIL_20` con un modelo real
del registry, no solo el sintético del test. `.onnx` de verificación
borrado tras la comprobación (no es un artefacto del repo).

Nota menor: `modelado/export/CONTRATO.md` da como ejemplo un panel
`panel_calidad_aire_grafo.parquet` que **no existe** en este entorno — el
export real (arriba) funciona con el panel normal vía el fallback k-NN de
`train_stgnn._preparar` sin necesitar ese fichero. No es un bug (el
fallback funciona), pero el comando de ejemplo del contrato no es
literalmente reproducible tal cual está escrito.

## 2. Tabla 3 — no es solo "está desactualizada", los números son volátiles día a día

`VIKT_05`/`VIKT_09` ya encontraron que Tabla 3 no reproduce con el código
actual. Esta pasada fue más allá: **se ejecutó de verdad**
`python -m modelado.evaluation.estudios.run_all --mlflow vic17-refresco`
contra los paneles reales ya materializados, para dar una recomendación
con evidencia, no solo una sospecha.

**Resultado (skill LightGBM vs. mejor línea base, hoy 30/8):**

| Fuente | h | Tabla 3 (memoria) | Reproducido hoy |
|---|---|---|---|
| Calidad del aire | 1 | 0,29 | **-0,159** |
| Calidad del aire | 3 | 0,58 | **-0,129** |
| Calidad del aire | 6 | 0,68 | 0,242 |
| Tráfico | 1 | 0,37 | 0,338 |
| Tráfico | 3 | 0,61 | 0,580 |
| Tráfico | 6 | 0,76 | 0,746 |

**Tráfico** reproduce razonablemente cerca (variación normal día a día).
**Calidad del aire es donde está el problema real** — y es más grave de
lo que sugería el diagnóstico anterior: no es que el número esté
desactualizado a un valor *mejor* que hoy no se alcanza, es que **hoy el
modelo entrenado desde cero rinde peor que la persistencia en 2 de 3
horizontes** (skill negativo).

**Confirmado independientemente**: estos números de hoy coinciden
exactamente con los que registró el propio cron de reentrenamiento
nocturno real esta madrugada (`modelado/evaluation/artifacts/nightly/historial.csv`,
fila `2026-08-30,calidad_aire,{1,3,6}`) — no es un artefacto de esta
ejecución puntual, es lo que el sistema en producción ya midió y por lo
que **no promocionó** el modelo de hoy (`promovido=False` para h1/h3,
correcto: la guarda de regresión está protegiendo al `@champion` vigente
de un día malo).

### Por qué "simplemente refrescar la tabla" no es la recomendación correcta

Sustituir los números de la Tabla 3 por los de "hoy" cambiaría la
narrativa de "el modelo bate a la línea base" a "el modelo pierde contra
la línea base a 1-3h" — **no porque el modelo esté mal diseñado**, sino
porque el skill día a día es genuinamente volátil con esta ventana de
datos (exactamente lo que el propio §7.4/backtest de la memoria ya
documenta: el skill a 6h de calidad del aire osciló entre 0,11 y 0,80 en
distintos días de backtest). Publicar el número de un solo día
(cualquier día, el de la memoria o el de hoy) es parcialmente arbitrario.

## Recomendación concreta

1. **No sustituir Tabla 3 por los números de un solo día nuevo** — sería
   cambiar un número potencialmente desactualizado por otro igual de
   frágil, solo que peor.
2. **Mejor opción**: correr `modelado.evaluation.backtest` para calidad
   del aire (y tráfico, para comparar) y publicar en Tabla 3 el skill
   **medio del backtest** (o un rango, "0,11–0,80 según el día, media
   X") en vez de un punto único — es más honesto y más robusto a qué día
   se ejecute antes de la entrega, y encaja con la evidencia de varianza
   que §7.4 ya reconoce.
3. Si se prefiere mantener un número puntual por simplicidad editorial,
   **decirlo explícitamente en el pie de tabla**: "medido el DD/MM;
   varianza día a día documentada en §7.4" — para que no parezca una
   cifra fija y definitiva cuando no lo es.
4. Esto es una decisión de contenido de memoria, no de código — se dejan
   los artefactos ya regenerados en `modelado/evaluation/artifacts/estudios/`
   (véase el commit de este ticket) como evidencia real disponible para
   quien decida, sin forzar ninguna edición del `.docx` aquí.

## Suite de tests

`modelado/tests/` completa (incluido `test_ml07.py::StgnnOnnxExportTests`)
sigue en verde con el entorno actual (`torch` CPU tras `FIL_23`) —
verificado de nuevo.
