---
kind: vic-eval
title: "Memoria — §7.1–7.3 Resultados, métricas, comparativas: releer números reales + diagrama del pipeline de modelado"
owner: Claude (Memoria)
status: pending
created_at: "2026-09-15"
depends_on: []
---

## Contexto

`VIC_05`/`VIKT_03` reconstruyeron Tabla 3 (métricas reales) y §7.3
(comparativas + explicabilidad) con los números de `ML_08`
(`run_all.py`). `VIC_38` añadió después la subsección de analítica de
grafo (centralidad + resiliencia) justo antes de §7.4. Nada de `FIL_69`-`99`
parece tocar `modelado/` directamente (son todos de la capa de
explotación), así que el riesgo de drift numérico aquí es más bajo que en
`VIC_50` — pero hay que confirmarlo, no asumirlo, y falta un diagrama que
explique el pipeline de modelado en sí (hoy solo se describe en prosa y en
el Anexo C como lista de comandos).

## Alcance

1. Confirmar que ningún ticket reciente tocó `modelado/` (`git log --
   modelado/` desde el commit de `VIC_38` hasta hoy) — si algo cambió,
   releer si Tabla 3/§7.3 siguen siendo exactas.
2. Releer §7.1 (logros) y §7.2 (métricas) por precisión y redacción —
   riesgo bajo, pase de confirmación más que de reescritura.
3. Releer la subsección de analítica de grafo que añadió `VIC_38`
   (centralidad + resiliencia + Figura 2) — confirmar que sigue siendo
   coherente tras las correcciones de `FIL_85`/`86`/`89` (ya aplicadas) y
   que no quedó ningún cabo suelto de esas correcciones sin reflejar aquí.
4. **Diagrama**: un diagrama del pipeline de `modelado/` (feature store →
   splits/CV temporal → líneas base → Tier 1 (LightGBM+SHAP) / Tier 2
   (STGNN) → MLflow (tracking+registry, alias `@champion`) → Evidently
   (deriva) → export ONNX → servido por el asistente), con los nombres de
   módulo reales (`modelado/features/`, `modelado/training/`, etc.) como
   etiquetas — ayuda a un lector a situar cada cifra de Tabla 3 en el
   proceso que la produjo. Usar `graphviz`, mismo criterio que el resto de
   la ronda.

## Fuentes técnicas

`modelado/README.md`, `modelado/evaluation/artifacts/estudios/`,
`doc/ML-01` a `doc/ML-10`, Anexo C del propio `.docx` (ya lista los
módulos y comandos — el diagrama es la versión visual de esa lista).

## Criterios de aceptación

- Confirmado (con `git log`) que no hay drift numérico desde `VIC_38`, o
  corregido si lo hay.
- Diagrama del pipeline de modelado insertado, coherente con Anexo C.
- Sin duplicar contenido entre el diagrama nuevo y la Figura 2 ya
  existente (resiliencia) — son cosas distintas, mantenerlas así.
