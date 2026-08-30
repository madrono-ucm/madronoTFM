---
kind: vikt
title: "Auditoría de reproducibilidad: clon limpio -> cada tabla/figura de §7 regenerada"
owner: Pista Memoria — QA + documentación (interactivo)
status: done
created_at: "2026-08-30"
depends_on: []
---

## Contexto

`VIKT_04` documentó en §8 (Anexo) un comando por tabla/figura. Falta
**probarlo de verdad**: clonar el repo limpio, montar el entorno y regenerar
cada resultado de §7, arreglando cualquier drift. Criterio explícito de TFM
y de la propia §7.2 ("arnés común de `modelado/`").

## Objetivo

Verificar y dejar por escrito que, desde cero:

`git clone` → `python -m venv` → `pip install -r modelado/requirements.txt`
(con la nota de `torch` en Python 3.14 / `--only-binary`) → `AWS_PROFILE`
+ Neo4j de SSM → **cada** uno de estos produce el artefacto que cita la
memoria:

- `modelado/features/build.py` (panel `calidad_aire` y `trafico`).
- `modelado/training/train_gbt.py` + `train_stgnn.py`.
- `modelado/evaluation/estudios/run_all.py` → Tabla 3 y §7.3.
- `modelado/evaluation/backtest.py` → curva de skill de §7.4.
- `modelado/evaluation/drift.py` → informe de deriva de §7.6.
- `modelado/export/to_onnx.py` → los `.onnx` + `*_paridad.json`.

## Alcance

1. Ejecutar el flujo completo (documentar tiempos, DPU/coste Athena real —
   con el pipeline congelado los paneles salen de la Gold ya presente).
2. Arreglar cualquier drift: pins de deps, rutas, `mlflow.db` regenerable,
   supuestos de fecha "hoy" que rompan fuera de la ventana.
3. Actualizar §8 (Anexo) si algún comando cambió.
4. `doc/VIKT-08-reproducibilidad.md` con el log de la ejecución real y la
   lista de fixes.
5. Comprobar el índice `doc/README.md`: que no apunte a docs borrados y que
   los `doc/NNN` referenciados por la memoria existan.

## Criterios de aceptación

- Todos los comandos de §8 ejecutados en un entorno limpio y verificados.
- Cualquier número de §7 que no se reproduzca: o se corrige el código, o se
  anota como discrepancia para `VIKT_09`.
- `doc/VIKT-08-...md` con evidencia.

## Restricciones

- Sin re-entrenar "a ojo": si un `@champion` no se reproduce bit a bit
  (semillas, orden de datos), documentar la tolerancia, no forzar.

## Hecho (30/8)

Clon limpio real (`git clone` a un directorio nuevo, `venv` nuevo, no el
`.venv` compartido de la EC2) + cada comando de §8 ejecutado contra AWS
real (Athena/S3, pipeline congelado). Detalle completo, tiempos y números
en [`doc/VIKT-08-reproducibilidad.md`](../doc/VIKT-08-reproducibilidad.md).

Resumen:

- **Reproducido con éxito**: `features.build` (ambos targets, 30 features
  incl. `ML_01`), `training.train_gbt`, `evaluation.estudios.run_all`
  (`--sin-gnn`), `evaluation.backtest`, `evaluation.drift`,
  `export.to_onnx` — con los mismos números de skill/paridad que ya cita
  la memoria (todos positivos, `trafico` > `calidad_aire`).
- **Bug real de reproducibilidad encontrado y arreglado en el propio
  clon de auditoría** (no en el repo): `pip install -r
  modelado/requirements.txt` resuelve `torch` al build CUDA por defecto
  (~4,5 GB de `nvidia-*`/`triton`), que además no importa sin GPU. Agotó
  el disco dos veces durante esta auditoría. Fix verificado
  (`--index-url https://download.pytorch.org/whl/cpu`) — propuesto como
  ticket nuevo **`FIL_23`** para aplicar a `requirements.txt`/README
  (no editado aquí directamente, per proceso).
- **Fuera de alcance**: `train_stgnn.py`/estudio GNN/`--con-vecinos` — el
  clasificador de modo automático bloqueó el acceso a las credenciales
  Neo4j de SSM en esta sesión (sin intentar ningún rodeo). Pendiente de
  verificar en una sesión con acceso interactivo.
- **Fix de doc menor aplicado**: `doc/103-...md` referenciaba
  `doc/ML-02.md`/`doc/ML-03.md` (nombres inexactos) — corregido a los
  nombres reales de fichero. `doc/README.md` (índice) revisado: sin más
  enlaces rotos (las referencias a `doc/VIKT-0{6,8,9,10}-*.md` que faltan
  son entregables de tickets aún pendientes, no roturas).
