---
id: 103
slug: modelado-ci-y-dependencia-sistema-libgomp
title: 'QA: modelado/ (el track de ML) no está en la CI, y LightGBM falla en esta
  EC2 por una librería de sistema ausente'
status: done
force: true
allow_infra_apply: false
branch: task/103-modelado-ci-y-dependencia-sistema-libgomp
pr_number: 162
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/162
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-29T12:00:00+00:00'
updated_at: '2026-08-29T10:47:21.700017+00:00'
started_at: '2026-08-29T10:44:06.556792+00:00'
submitted_at: '2026-08-29T10:46:14.534022+00:00'
merged_at: '2026-08-29T10:46:18Z'
---

## Contexto

Verificando si `VIC_05` podía avanzar (necesita las salidas reales de
`ML_03`/Tier 1 y `ML_05`/Tier 2), se auditó el estado real de
`ML_01`–`ML_03` — cuyo `status:` en el front-matter seguía en `pending`
pese a que el cuerpo de cada ticket ya decía "HECHO". Verificado
independientemente (no solo confiando en la nota del ticket):

- `modelado/tests/test_ml02.py` (splits/baselines/métricas): **8/8 tests
  en verde**, sin cambios.
- `modelado/tests/test_ml03.py` (Tier 1 LightGBM/SHAP): **fallaba al
  importar** con `OSError: libgomp.so.1: cannot open shared object file` —
  no un bug de código, sino que esta EC2 no tiene instalada la librería de
  sistema `libgomp1` (runtime de OpenMP, dependencia nativa de LightGBM).
  Instalada con `sudo apt-get install -y libgomp1` → los 3 tests pasan
  limpios. Sin este paso, **cualquier sesión nueva en esta EC2 que instale
  `modelado/requirements.txt` y corra los tests de `ML_03` los verá fallar
  igual**, y podría malinterpretarlo como una regresión real.
- Los artefactos reales de `ML_03` (`modelado/evaluation/artifacts/
  tier1_{calidad_aire,trafico}.csv`, SHAP) contienen métricas verosímiles
  (LightGBM bate a la mejor línea base en los tres horizontes, skill score
  0.29–0.78) — confirma que el entrenamiento real sí se ejecutó en algún
  momento (en un entorno que sí tenía `libgomp1`, o instalado a mano sin
  dejarlo documentado).
- `.github/workflows/ci.yml` (tarea 097) **no incluye `modelado/` en
  absoluto** — solo corre `pytest ingesta/ procesamiento/ grafo/
  asistente/ herramientas/`. El track de ML, descrito en `NEXT_STEPS.md`
  como "el elemento central del TFM", es el único módulo del proyecto sin
  ninguna cobertura automática de tests.
- Corregido de paso el front-matter desactualizado: `ML_02`/`ML_03` →
  `status: done` (confirmado); `ML_01` se deja en `status: pending` (su
  propia nota ya admite gaps reales: falta el join real de meteo/previsión
  AEMET y el calendario de festivos real).

## Objetivo

Cerrar el hueco de reproducibilidad (`libgomp1`) y el de cobertura (CI)
para que el track de ML tenga las mismas garantías que el resto del
proyecto.

## Alcance concreto

1. Añadir `modelado/` al job `tests` de `.github/workflows/ci.yml`,
   instalando `modelado/requirements.txt` igual que los otros módulos.
   **Nota de coste/tiempo**: `torch`/`lightgbm`/`mlflow` son pesados;
   verifica que el runner de GitHub Actions (`ubuntu-latest`) no tenga el
   mismo problema de `libgomp1` (probablemente no, las imágenes de GitHub
   Actions ya lo incluyen, pero verifícalo en el propio run en vez de
   asumirlo) y que el tiempo total de CI siga siendo razonable.
2. Si `libgomp1` faltara también en el runner de CI, añade el paso
   `apt-get install -y libgomp1` explícito antes de instalar
   `requirements.txt`.
3. Documenta en `modelado/README.md` la dependencia de sistema
   `libgomp1` (LightGBM) como prerrequisito, para que la próxima sesión
   interactiva en una EC2 nueva no pierda tiempo diagnosticando el mismo
   error.
4. Documenta en `doc/103-...md` el hallazgo y la corrección.

## Restricciones

- No toques la lógica de `modelado/` — es un problema de entorno/CI, no de
  código.
- No instales `torch`/`mlflow` en esta EC2 si el disco sigue ajustado
  (`df -h /` estaba al 95% tras instalar solo las dependencias ligeras de
  `ML_01`–`ML_03`) — verifica espacio libre antes; si no cabe, documenta el
  hallazgo igualmente a partir de lo ya verificado (`ML_02`/`ML_03` en
  verde) sin necesidad de re-verificar `ML_04`/`ML_05` en esta misma
  tarea.

## Criterios de aceptación

- `modelado/` corre en la CI de cada PR/push, igual que el resto de
  módulos.
- `modelado/README.md` documenta `libgomp1` como prerrequisito de sistema.
- `doc/103-...md` documenta el hallazgo (incluida la corrección de
  `status` en `ML_02`/`ML_03`, ya aplicada en este commit).
- Hay un commit real.
