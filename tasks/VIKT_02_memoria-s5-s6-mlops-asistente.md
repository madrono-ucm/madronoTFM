---
kind: vikt
title: "Memoria §5.4/§5.5 + §6.7/§4.1 — MLOps real y bucle del asistente (post ML_04-10)"
owner: Pista Memoria — documentación (interactivo)
status: done
done_by: "Claude (Sonnet 5)"
done_at: "2026-08-29"
depends_on: [VIKT_01]
created_at: "2026-08-29"
---

## Objetivo

Incorporar al `.docx` el material de `ML_04`, `ML_06`, `ML_07`, `ML_09` y
`ML_10` en las secciones de arquitectura/DevOps y de explotación, según lo
que marque `VIKT_01`.

## Secciones y cambios

- **§5.5 Estrategia DevOps / MLOps**: describir el ciclo real —
  - MLflow con **backend SQLite local** (`modelado/mlflow.db`), experimentos
    por *tier*, **registro de modelos con alias `@champion`** (no *stages*);
    coste 0, migrable a un servidor con `MLFLOW_TRACKING_URI` (`doc/ML-04`).
  - **Evidently** como informe de deriva *bajo demanda* (PSI + KS + informe
    `DataDriftPreset`), no un servicio en vivo — con el resultado real
    (`doc/ML-06`).
  - **ONNX** como formato de despliegue: export desde el registro, **test de
    paridad** nativo↔ONNX con tolerancia documentada, contrato de entrada en
    `modelado/export/CONTRATO.md` (`doc/ML-07`).
  - **Reentrenamiento nocturno** vía `cron` en la EC2 (coste 0, sin
    Terraform) + backtest incremental (`doc/ML-10`, `infra/OPERACION.md`).
- **§5.4 Costes** (Tabla 2): confirmar que nada de lo anterior añade coste
  (SQLite, cron, `onnxruntime` en CPU) — ajustar el texto si hiciera falta.
- **§6.7 Explotación**: **«seis herramientas» → «siete»**; añadir
  `calidad_aire_prevista` — sirve una **previsión** de calidad del aire a
  1/3/6 h corriendo el modelo ONNX, anclada al último dato real de Gold,
  con fiabilidad degradada si faltan features (`doc/ML-09`). Ninguna tool
  con `NotImplementedError`.
- **§4.1 Diseño general**: cerrar explícitamente el bucle
  *observación → predicción → asistente* que el diseño planteaba —
  `ML_09` lo materializa.

## Fuente técnica

`doc/ML-04`, `doc/ML-06`, `doc/ML-07`, `modelado/export/CONTRATO.md`,
`doc/ML-09`, `doc/ML-10`, `asistente/README.md`, `infra/OPERACION.md`,
`modelado/README.md`. El informe de `VIKT_01`.

## Criterios de aceptación

- §5.5 describe MLflow-registry + Evidently + ONNX + nightly como están
  construidos (no como capa genérica), con al menos un número real por
  pieza.
- §6.7 dice «siete herramientas» y describe la de previsión.
- Sin afirmación nueva que `VIKT_01` no haya validado contra el repo.
- Estilos y numeración del `.docx` intactos (editar con `python-docx`).

## Restricciones

- Coordinar el turno del `.docx` (ver `VIKT_00`). `git pull` antes.

## Hecho (29/8)

§4.1 (cierra el bucle con `calidad_aire_prevista`), §5.4 (nota de coste 0
del pipeline de modelado), §5.5 (MLflow SQLite+`@champion`, Evidently bajo
demanda con el resultado real, ONNX+CONTRATO.md con la cota de paridad,
reentrenamiento nocturno vía cron) y §6.7 (siete herramientas, ya sin el
condicional "cuando esté disponible") reescritas en
`documents/Memoria_TFM FV.docx`, con cada cifra tomada de `doc/ML-04`,
`doc/ML-06`, `doc/ML-07`, `doc/ML-09`, `doc/ML-10` según señaló `VIKT_01`.
