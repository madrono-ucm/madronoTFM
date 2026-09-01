---
kind: vikt-index
owner: Pista Memoria — QA + documentación (interactivo)
created_at: "2026-08-29"
---

# `VIKT_*` tickets — QA de la memoria + documentación del trabajo post-`VIC_*`

Los 7 tickets `VIC_*` reescribieron `documents/Memoria_TFM FV.docx` a la
arquitectura real (29/8), pero se cerraron cuando de la pista de ML solo
existían `ML_02`/`ML_03`/`ML_05`. Después han aterrizado **`ML_04`, `ML_06`,
`ML_07`, `ML_08`, `ML_09` y `ML_10`** (PRs #159–#168) con material nuevo que
la memoria aún no refleja del todo, y hace falta una **pasada de QA** que
verifique cada afirmación contra el repo tal como está hoy.

Fuera de la cola autónoma del `madrono-agent` (igual que `VIC_*`/`FIL_*`/
`ML_*`: el demonio solo coge `^\d+-[a-z0-9-]+\.md$`).

## Coordinación (`.docx` no se fusiona en git)

`documents/Memoria_TFM FV.docx` es binario: **no se edita a la vez desde dos
sitios** (ver `PLAN.md` §"Memoria — reparto"). `VIKT_01` es solo análisis
(produce un informe en `doc/`, no toca el `.docx`). `VIKT_02`–`VIKT_04`
editan el `.docx` con `python-docx` (preserva estilos/numeración); avisar en
el chat antes de tocarlo y hacer `git pull` primero.

## Tickets

| Ticket | Qué | Toca `.docx` | Depende de |
|---|---|---|---|
| `VIKT_01` | **QA sweep**: reconciliar todo el cuerpo de la memoria con el repo a fecha `ML_10`. Tabla de discrepancias + grep de términos obsoletos. Deja `doc/VIKT-01-qa-memoria.md` | No | ✅ **HECHO 29/8** — 14 discrepancias (2 media-alta), grep limpio, sin datos inventados. Repartidas a `VIKT_02/03/04` |
| `VIKT_02` | §5.4/§5.5 (DevOps/MLOps) + §6.7/§4.1 (explotación/asistente): incorporar `ML_04` (registro + `@champion`), `ML_06` (deriva), `ML_07` (ONNX + `CONTRATO.md` + paridad), `ML_09` («seis»→«siete» tools, bucle de previsión), `ML_10` (reentrenamiento nocturno vía cron) | Sí | ✅ **done 29/8 (Claude)** |
| `VIKT_03` | §7.1–7.4: consolidar Tabla 3 y §7.3 con la salida de `ML_08` (`run_all.py`), añadir a §7.4 la **curva de backtest incremental** de `ML_10` como evidencia de la ventana corta + la cota de paridad de `ML_07` + el resultado de deriva de `ML_06`. §7.5: `STGNN`→ONNX y `afluencia_prevista` como líneas futuras | Sí | ✅ **done 29/8 (Claude)** — Tabla 3 tráfico actualizada a los números consolidados de `run_all.py`, con footnote de scope |
| `VIKT_04` | §8 Anexo — **reproducibilidad**: un comando por tabla/figura (`estudios/run_all.py`, `evaluation/backtest.py`, `export/to_onnx.py`, `training/retrain_nightly.py`, `evaluation/drift.py`), el layout de `modelado/` y `asistente/modelos/`, `mlflow ui`, la línea de `cron` | Sí | ✅ **done 29/8 (Claude)** |
| `VIKT_05` | §7.5 — el gap de `ML_01` (meteo/festivos) que describe como "sin implementar" ya tiene código y tests reales (`modelado/features/exogenas.py`), encontrado en la ronda de evaluación técnica `VIC_08`-`15` | Sí | ⬜ pendiente — matiz importante antes de editar: confirmar si la Tabla 3 actual ya se entrenó con estas features o no |
| `VIKT_06` | **Recorrido e2e reproducible para la defensa**: muestra→pipeline→Gold→grafo→asistente + previsión ML. `doc/VIKT-06-...md` + material de screencast | No | ⬜ pendiente — depende de `FIL_13`/`FIL_15` |
| `VIKT_07` | §7.4 — **lista consolidada de limitaciones** (post-congelación): ventana corta, pipeline congelado 30/8, STGNN sin ONNX servible, sin alertado, EMT 1 parada, avisos verdes, auth de bluesky, afluencia fina, hueco 29/8 ya backfilled | Sí | ⬜ pendiente — depende de `VIKT_09` |
| `VIKT_08` | **Auditoría de reproducibilidad**: clon limpio → cada tabla/figura de §7 regenerada; arreglar drift; verificar `doc/README.md`. Extiende `VIKT_04` | Sí (anexo) | ⬜ pendiente |
| `VIKT_09` | **Pasada final memoria↔código** en el commit de entrega (post `FIL_11`–`FIL_19` + congelación). Metodología de `VIKT_01` | Sí | ⬜ pendiente — última antes de `VIKT_10` |
| `VIKT_10` | **Revisión editorial humana** del `.docx` + **preparación de la defensa** (guion + Q&A: por qué no Kafka / por qué congelado / por qué STGNN no servido) | Sí | ⬜ pendiente — requiere humano |
| `VIKT_11` | Incorporar los **deltas del 2026-09-01**: `FIL_17` (secretos runtime) pasó de "diseñado" a aplicado+verificado; `FIL_16` observabilidad parcialmente desplegada (regla EventBridge activa, sink SNS diferido); `FIL_55` arregló el panel de resumen del mapa publicado; ventana de re-congelación del pipeline | Sí | ⬜ pendiente — depende de `VIC_33` (verificación AWS) y coordina con `VIKT_09` |

## Fuentes técnicas (leer antes de escribir)

- `doc/ML-04` … `doc/ML-10`, `modelado/export/CONTRATO.md`, `doc/ML-09`.
- `modelado/README.md`, `asistente/README.md`, `infra/OPERACION.md`.
- Artefactos reales: `modelado/evaluation/artifacts/estudios/`,
  `.../backtest/`, `.../drift/`, `modelado/export/artifacts/*_paridad.json`.
- `NEXT_STEPS.md` (§3 tabla estado, §5.3 diseño ML, decisión 8).

## Lo que ya está bien en la memoria (no reabrir sin motivo)

`VIC_*` dejó §5.2 (pila real, sin Kafka/Delta), §6.1–6.6 (fuentes/flujos),
§7.2 Tabla 3 (con LightGBM + STGNN reales), §7.3 (ablaciones de decisión 8
descartadas de forma explícita), §7.4 (7 limitaciones), §7.5 (10 líneas
futuras) y §1–4 (pasada de consistencia). `VIKT_*` **añade y corrige**, no
reescribe.
