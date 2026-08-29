---
kind: vikt
title: "QA sweep — reconciliar la memoria con el repo a fecha ML_10"
owner: Pista Memoria — QA (interactivo)
status: done
depends_on: [ML_02, ML_03, ML_04, ML_05, ML_06, ML_07, ML_08, ML_09, ML_10]
created_at: "2026-08-29"
---

> **Estado 29/8: ✅ HECHO.** Informe en `doc/VIKT-01-qa-memoria.md`.
> Veredicto: la memoria está estructuralmente sana y sin datos inventados;
> 14 discrepancias (2 media-alta: §6.7 «seis»→«siete» tools + previsión ya
> servida; Tabla 3 tráfico no reproducible desde `run_all.py` por *scope*).
> El grep de términos obsoletos sale limpio (todos legítimos salvo
> "esquemas Avro" en el Anexo C). Discrepancias repartidas a
> `VIKT_02`/`VIKT_03`/`VIKT_04`. Fix trivial aplicado en
> `infra/terraform/lambda.tf` (comentario 14→16 productores).

## Objetivo

Antes de tocar el `.docx`: una pasada de QA que verifique **cada afirmación
cuantitativa o de estado** del cuerpo de la memoria contra el repo tal como
está tras `ML_10`. No edita la memoria — produce el informe que guía a
`VIKT_02`–`VIKT_04`.

## Alcance

- Leer `documents/Memoria_TFM FV.docx` con `python-docx` (solo lectura).
- **Grep de términos obsoletos / de estado** en todo el cuerpo:
  `seis herramientas` / `6 tools`, `Kafka`, `Avro`, `Flink`, `KSQL`,
  `streaming`, `Delta Lake`, `Power BI`, `populartimes`, `Google`, `24
  fuentes` vs `14 en producción`, `tres y cuatro semanas`, cualquier `TODO`
  o marcador.
- **Cross-check de números**: cada celda de la Tabla 3 contra
  `modelado/evaluation/artifacts/estudios/comparacion_todos.csv` y
  `doc/ML-08`; los valores de skill/MAE citados en §7.1–7.3 contra
  `doc/ML-03`/`doc/ML-05`; la estimación de costes §5.4 contra la realidad
  (MLflow SQLite local, cron en EC2, sin recursos nuevos de pago).
- **Cross-check de estado**: §5.5 (MLflow/Evidently/ONNX descritos como
  reales) contra `doc/ML-04`/`ML-06`/`ML-07`; §6.7 (nº de tools del
  asistente, mención de previsión) contra `asistente/README.md` +
  `doc/ML-09`; §7.4 (limitaciones) — ¿falta la evidencia de backtest de
  `ML_10`, la cota de paridad de `ML_07`, el resultado de deriva de
  `ML_06`?; §7.5 (líneas futuras) — ¿falta `STGNN`→ONNX (bloqueado por
  `torch.export`) y `afluencia_prevista`?
- Revisar que las **3 tablas** y las figuras referenciadas existan y sus
  pies/numeración cuadren.

## Entregable

`doc/VIKT-01-qa-memoria.md` con:

1. Tabla de discrepancias: `sección | afirmación en la memoria | realidad
   (con fuente) | severidad (alta = dato falso / media = desactualizado /
   baja = matiz) | arreglo propuesto | ticket VIKT que lo cierra`.
2. Resultado del grep de términos obsoletos (línea y contexto de cada
   acierto, marcando si es legítimo — p. ej. en §7.5 como línea futura — o
   un residuo).
3. Lista de material de `ML_04`–`ML_10` **no mencionado** en la memoria y
   dónde debería ir.
4. Un veredicto: ¿la memoria está lista para entrega salvo los arreglos de
   `VIKT_02`–`VIKT_04`, o hay algo de severidad alta?

## Criterios de aceptación

- El informe cubre §1–§8 (no solo §5/§7).
- Cada discrepancia tiene una fuente concreta del repo (`doc/`, artefacto,
  README) — no "creo que".
- Las entradas quedan asignadas a `VIKT_02`, `VIKT_03` o `VIKT_04`.

## Restricciones

- **No editar el `.docx`.** Solo lectura + informe en `doc/`.
