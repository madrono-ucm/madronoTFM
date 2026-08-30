# VIKT-08 — Auditoría de reproducibilidad de `modelado/` desde un clon limpio

Ejecutado 2026-08-30 (`tasks/VIKT_08_auditoria-reproducibilidad-modelado.md`,
parte de `doc/PLAN-REVISION-TFM.md`). Objetivo: `git clone` limpio + entorno
nuevo + seguir literalmente `modelado/README.md`/§8 del anexo, regenerando
cada tabla/figura que cita la memoria, y documentar cualquier drift.

## Entorno

- Clon limpio en `/home/ubuntu/vikt08-work/repo` (fuera de los repos de
  trabajo habituales), `venv` nuevo, **no** el `.venv` compartido de la EC2
  interactiva (que ya tenía parches ad-hoc de sesiones anteriores — el
  objetivo era probar el camino "desde cero" real).
- `Python 3.14.4`, `libgomp1` ya presente en el sistema (`dpkg -l` lo
  confirma) — no hizo falta instalarlo.
- Autenticación AWS: **no** hace falta `AWS_PROFILE=madrono` en esta EC2 —
  el rol de instancia (`madrono-terraform-deployerEC2`, vía IMDS) ya
  autentica `boto3` sin ninguna variable. La nota de `AWS_PROFILE=madrono`
  del README aplica a un puesto de trabajo local con perfil nombrado, no a
  esta máquina.
- Neo4j (SSM `secrets/neo4j-*`): **bloqueado en esta sesión** — el
  clasificador de modo automático de Claude Code deniega cualquier
  `aws ssm get-parameter --with-decryption` de un secreto, incluso sin
  imprimir el valor. No se intentó ningún rodeo. Efecto en el alcance de
  esta auditoría: **no se pudo ejercer `--con-vecinos` (features de vecinos
  de grafo) ni construir los paneles `*_grafo.parquet`, y por tanto tampoco
  `train_stgnn.py` ni el estudio GNN de `run_all.py`** (se corrió con
  `--sin-gnn`). Esto debe verificarse aparte, en una sesión con acceso
  interactivo a las credenciales de Neo4j.

## Hallazgo real de reproducibilidad: `torch` resuelve a CUDA, no a CPU

Ver **`FIL_23`** (ticket nuevo, con el diagnóstico completo y el fix
propuesto). Resumen: `pip install -r modelado/requirements.txt` en un clon
limpio, sin más, descarga el build CUDA por defecto de `torch` (~4.5 GB de
`nvidia-*`/`triton`), que:

1. Agotó el disco dos veces en esta misma auditoría (primero en `/tmp`
   tmpfs de 1.9G, después en el disco real de la EC2, de 9.4G libres a 0).
2. No importa en runtime sin GPU (`libcudart.so.13`/`libcublasLt.so` no
   encontrados) — es decir, ni siquiera sirve de nada tras el coste de
   descargarlo.

Fix verificado: `pip install --index-url https://download.pytorch.org/whl/cpu torch`
antes/en vez del `torch` normal del `requirements.txt` — tras eso, build
`2.13.0+cpu`, 757M (sin `nvidia`/`triton`), y **todo lo demás de esta
auditoría corrió sin ningún otro problema** contra ese build. No se ha
editado `requirements.txt`/`README.md` en este ticket (`FIL_23` lo propone
para revisión).

## Ejecución real, comando por comando (§8 del anexo)

Todos los comandos siguientes se ejecutaron contra AWS real (Athena/S3),
con el pipeline de ingesta congelado (`pipeline_enabled=false`, ver
`infra/OPERACION.md`) — es decir, los paneles salen de la Gold ya
presente, sin ningún job de Glue disparándose.

| # | Comando | Resultado | Tiempo |
|---|---|---|---|
| 1 | `python -m modelado.features.build --target calidad_aire --desde 2026-08-15 --hasta 2026-08-29 --out .../panel_calidad_aire.parquet` | OK — 43.878 filas, 123 entidades, 30 features (incl. `meteo_*`/`prev_*`/`es_festivo` de `ML_01`) | 6,7s |
| 2 | ídem `--target trafico` | OK — 1.659.648 filas, 4.704 entidades, 30 features | 40,8s |
| 3 | `python -m modelado.training.train_gbt --panel .../panel_calidad_aire.parquet --nombre calidad_aire --mlflow tier1` | OK — LightGBM registrado en MLflow (`madrono-calidad_aire-h{1,3,6}`), bate a la persistencia/climatología en los 3 horizontes | 2m20s |
| 4 | `python -m modelado.evaluation.estudios.run_all --sin-gnn --mlflow tier1-estudios` | OK — regenera `comparacion_{calidad_aire,trafico,todos}.csv`, `explicabilidad_*.json`, `skill_*.png` (ver tabla de skill abajo) | ~10min (dominado por `trafico`, 1,66M filas) |
| 5 | `python -m modelado.evaluation.backtest --panel .../panel_calidad_aire.parquet --target calidad_aire` | OK — 24 puntos de backtest, curva de skill por fecha_corte (mejora con más datos, con algo de ruido día a día — igual que documenta `ML_10`) | 4m32s |
| 6 | `python -m modelado.evaluation.drift --panel .../panel_calidad_aire.parquet --target calidad_aire` | OK — PSI/KS reales, 12/30 features con deriva significativa (mayormente calendario/meteo, por la ventana corta — coherente con §7.4) | 27s |
| 7 | `python -m modelado.export.to_onnx --modelo madrono-calidad_aire-h6 --panel .../panel_calidad_aire.parquet --nombre calidad_aire_h6` | OK — `.onnx` de 1.361.140 bytes, paridad nativo↔ONNX mean=0,09% p99=1,05% (dentro de tolerancia 0,5%/2%) | 18s |

**Números de skill reproducidos** (`comparacion_todos.csv`, LightGBM vs.
baseline):

| target | h | skill |
|---|---|---|
| calidad_aire | 1 | 0.0508 |
| calidad_aire | 3 | 0.1719 |
| calidad_aire | 6 | 0.2092 |
| trafico | 1 | 0.3225 |
| trafico | 3 | 0.5572 |
| trafico | 6 | 0.6837 |

Todos positivos (el modelo bate al baseline en los 6 casos), consistente
con lo que ya documenta la memoria §7.2/§7.3. `trafico` reproduce con
skill notablemente más alto que `calidad_aire` en los 3 horizontes.

**No ejecutado en esta auditoría** (fuera de alcance por el bloqueo de
Neo4j, ver arriba): `train_stgnn.py`, el estudio GNN de `run_all.py`
(`--con-gnn-trafico`), y cualquier panel con `--con-vecinos`.

## Otros fixes aplicados en esta pasada

- `doc/103-modelado-ci-y-dependencia-sistema-libgomp.md`: corregidas dos
  referencias inexactas (`doc/ML-02.md`/`doc/ML-03.md` → los nombres reales
  `doc/ML-02-splits-baselines-metricas.md`/`doc/ML-03-tier1-lightgbm-shap.md`).
  Encontrado auditando `doc/README.md` (índice de `doc/`) por enlaces rotos:
  fue el único real (el resto de referencias `doc/VIKT-0{6,8,9,10}-*.md`
  detectadas como "faltantes" son entregables de tickets aún pendientes,
  no enlaces rotos).

## Limitaciones de esta auditoría

- Alcance de Neo4j no verificado (ver arriba) — pendiente de una sesión con
  acceso interactivo a SSM.
- No se ha intentado reproducir bit a bit el `@champion` actual del
  registry de producción (`modelado/mlflow.db` real) — esta auditoría usó
  un registry SQLite nuevo y vacío en el clon limpio, así que compara
  *números* (skill, paridad) contra lo documentado, no *artefactos*
  binarios idénticos. Coherente con la restricción explícita del ticket
  ("sin re-entrenar a ojo... documentar la tolerancia, no forzar").
- `/home/ubuntu/vikt08-work/` (clon + venv + artefactos de esta auditoría)
  se limpia tras esta pasada — no forma parte del repo.
