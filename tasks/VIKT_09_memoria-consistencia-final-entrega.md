---
kind: vikt
title: "Pasada final memoria <-> código en el commit de entrega (post FIL_11-19 + congelación)"
owner: Pista Memoria — QA + documentación (interactivo)
status: pending
created_at: "2026-08-30"
depends_on: [FIL_13, FIL_14, FIL_15, FIL_16, FIL_17, FIL_18, FIL_19, VIKT_08]
---

## Contexto

`VIKT_01` hizo la última pasada de consistencia el 29/8 (estado `ML_10`).
Desde entonces: `FIL_09`–`FIL_12` (incidentes + backfill), `bluesky` con
auth, `exogenas.py`, la **congelación del pipeline**, y — según avancen —
`FIL_13`–`FIL_19`. La memoria hay que revisarla **contra el repo tal como
quede en el commit de entrega**, no antes.

## Objetivo

Repetir la metodología de `VIKT_01` (tabla de discrepancias + grep de
términos obsoletos + "sin datos inventados") sobre §5, §6 y §7 completos,
con foco en lo que ha cambiado:

- §5/§6: ¿el nº de tools del asistente ("siete") sigue vigente tras
  `FIL_13`/`FIL_14`? ¿La descripción de la capa de servicio de ML menciona
  `trafico_prevista`? ¿El envoltorio de respuesta de `FIL_15`?
- §6.x fuentes: `bluesky_menciones` (auth), `ruido`/`aemet_avisos`
  (`mode("overwrite")` dinámico, `doc/FIL-11`), `aemet_prevision` (Silver
  como fuente de la feature, `doc/ML-01`).
- §5.4/§5.5: ¿menciona alertado (`FIL_16`) y secretos en runtime (`FIL_17`)
  si se han hecho? ¿O quedan en §7.5?
- §7: números contra `VIKT_08`.
- **Grep de "en producción continua" / "cada hora" / "diariamente"** →
  cada uno debe convivir con la nota de congelación (30/8) o reformularse.

## Alcance

1. `doc/VIKT-09-consistencia-final.md` con la tabla de discrepancias.
2. Repartir los fixes: los de redacción menor, aplicarlos aquí con
   `python-docx`; los grandes, a `VIKT_07` (§7.4) o `VIKT_10` (editorial).

## Criterios de aceptación

- Cada afirmación de §5/§6/§7 tiene un `doc/`/fichero del repo que la
  respalda en el commit de entrega, o está en la tabla de discrepancias.
- Grep de términos obsoletos limpio.

## Restricciones

- Última en ejecutarse de la pista `VIKT_*` antes de `VIKT_10`. `git pull`
  + aviso antes de tocar el `.docx`.
