# ML-10 — Reentrenamiento nocturno + backtest incremental

Los datos crecen ~1 día/día hasta la entrega (17/9). ML_10 convierte eso en
una historia de resultados para §7 ("el modelo mejora según se acumulan
datos") y en un modelo que se mantiene fresco.

## Qué se creó

- **`modelado/evaluation/backtest.py`** — backtest de **rolling origin**:
  `backtest_incremental(panel, *, target, test_days=2, min_train_days=5,
  paso_dias=1)` — para cada fecha de corte `D`, entrena LightGBM (`ML_03`)
  con `[inicio, D-2d]`, evalúa en `(D-2d, D]`, registra `skill` vs
  persistencia por horizonte. `figura_skill_vs_fecha` traza la curva. CLI →
  `modelado/evaluation/artifacts/backtest/backtest_<t>.csv` +
  `skill_vs_fecha_<t>.png`.
- **`modelado/training/retrain_nightly.py`** — el job 1×/día: (opcional)
  regenera el panel (`ML_01`, `--rebuild-panel`), reentrena LightGBM,
  evalúa (`ML_02`), loguea el run en MLflow (`ML_04`, experimento
  `nightly`) y **promueve `@champion` solo si no regresa** respecto al
  vigente (`decidir_promocion`, función pura). Deja una fila por
  `(fecha, target, horizonte)` en
  `modelado/evaluation/artifacts/nightly/historial.csv`. Corre una vez y
  termina (guardrail de `tasks/README.md` — nada en bucle en disco local).
- **`modelado/tests/test_ml10.py`** — 6 tests (`decidir_promocion`:
  sin-vigente / mejor-promueve-peor-no / margen / NaN; backtest: columnas +
  `n_train` no decreciente con la fecha; la figura no rompe).

`python -m pytest modelado/ -q` → **45 passed**.

## Mecanismo de programación elegido — y por qué (coste 0)

**`cron` en la EC2 del demonio**. Es la opción de coste 0 que **no toca
Terraform** (EventBridge + Lambda exigiría `allow_infra_apply` para crear
esos recursos; `/schedule` de un agente cloud no está disponible de forma
estable). El script ya es idempotente y termina solo.

```cron
# /etc/cron.d/madrono-retrain  (EC2 del demonio)
30 3 * * *  ubuntu  cd /opt/madrono && AWS_PROFILE=madrono /opt/madrono/.venv/bin/python -m modelado.training.retrain_nightly --rebuild-panel >> /var/log/madrono-retrain.log 2>&1
```

Registrado también en `infra/OPERACION.md`. El backend de MLflow es el
SQLite local de `ML_04` (`modelado/mlflow.db`); si se quiere consultar el
historial desde fuera, `mlflow ui --backend-store-uri sqlite:///modelado/mlflow.db`.

## Resultados reales

### Backtest incremental — `calidad_aire` (skill vs persistencia)

| fecha de corte | h1 | h3 | h6 |
|---|---|---|---|
| 2026-08-22 | +0.13 | +0.44 | +0.63 |
| 2026-08-23 | +0.11 | +0.48 | +0.68 |
| 2026-08-24 | −0.04 | +0.28 | +0.46 |
| 2026-08-25 | −0.02 | +0.19 | +0.11 |
| 2026-08-26 | +0.11 | +0.51 | +0.56 |
| 2026-08-27 | +0.34 | +0.73 | +0.80 |
| 2026-08-28 | +0.31 | +0.72 | +0.73 |

21 puntos (7 fechas × 3 horizontes). La tendencia es **al alza** conforme
crece el histórico — con un bache real el 24–25/8 (dos días peores en los
datos, no un artefacto). Curva en
`modelado/evaluation/artifacts/backtest/skill_vs_fecha_calidad_aire.png`.
Es exactamente la evidencia que pide §7 sobre la ventana corta (§7.4): el
modelo aún no ha convergido, la señal de mejora está pero con varianza alta.

### Reentrenamiento nocturno — ejecución real (2026-08-29)

`python -m modelado.training.retrain_nightly --targets calidad_aire`:

| horizonte | skill nuevo | skill vigente | promovido |
|---|---|---|---|
| 1 | 0.293 | 0.293 | sí |
| 3 | 0.580 | 0.580 | sí |
| 6 | 0.675 | 0.675 | sí |

3 runs nuevos en el experimento `nightly` de MLflow; `@champion` movido a
las versiones nuevas (mismo skill → se promueve el reentreno más fresco;
`decidir_promocion` bloquea solo si **regresa**). Fila añadida a
`historial.csv`.

## Criterios de aceptación

- [x] El job de reentrenamiento corre de verdad y deja runs nuevos en
  MLflow (ejecución del 29/8, experimento `nightly`).
- [x] `backtest.py` produce la curva de skill a lo largo del tiempo (CSV +
  PNG) para calidad del aire.
- [x] `doc/` con el mecanismo de programación (cron en la EC2, coste 0) y el
  porqué.
- [x] No toca Terraform (mecanismo = cron, no EventBridge/Lambda).
- [x] Nada en bucle en disco local: el script corre una vez y termina.

## Notas

- La verificación es de una ejecución manual; instalar el `cron.d` en la EC2
  es el paso de despliegue (mismo patrón que el resto de `infra/OPERACION.md`).
- `--rebuild-panel` necesita `AWS_PROFILE=madrono` (Athena). Sin él, el job
  reentrenaría sobre el panel ya materializado (útil para probar el
  mecanismo sin credenciales).
- Extensión natural: incluir el STGNN (`ML_05`) en el nightly cuando su
  entrenamiento baje de ~40 min, y `trafico` (ya soportado, `--targets`).
