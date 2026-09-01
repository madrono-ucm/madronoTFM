# Plan de evaluación técnica — ronda 7 (deltas de ingeniería del 2026-09-01)

**Fecha:** 2026-09-01 · **Contexto:** las rondas 1-6 (`VIC_08`-`31`)
auditaron el estado del repo hasta finales de agosto. El 2026-09-01 una
sesión interactiva aterrizó tres cambios que ninguna ronda anterior ha
visto y que tocan zonas sensibles (frontend público + estado real de AWS):

1. **`FIL_55`** (PR #234, mergeado) — arregla el panel de resumen del
   mapa animado publicado, que lanzaba `TypeError` con las métricas
   virtuales de `FIL_45` (perfiles de sensibilidad / dosis) y congelaba
   media interfaz. Verificado solo con un **arnés headless jsdom** (sin
   navegador real) → falta una pasada en navegador de verdad.
2. **`FIL_17`** aplicado a AWS (`terraform apply -target`) — los 4
   productores con secreto dejan de exponer credenciales en claro en el
   env de la Lambda; ahora se leen de SSM en runtime. Verificado con un
   `invoke` real, pero conviene una **verificación independiente** contra
   AWS de que el estado es correcto y de mínimo privilegio.
3. **Pipeline reanudado ~24 min y RE-CONGELADO** + **`FIL_16` parcial**
   (regla EventBridge creada, sink SNS bloqueado por IAM, aceptado por el
   usuario). Hay que confirmar que el `terraform apply -target` **no dejó
   drift inesperado** y que el estado final es efectivamente "congelado".

Ninguna de estas rondas cambia código: son verificación. Cualquier
hallazgo con potencial de bug real → `FIL_*` nuevo (**numeración
siguiente: `56`**).

## Tickets

| # | Ticket | Ángulo |
|---|---|---|
| `VIC_32` | QA del mapa publicado tras `FIL_55` — **en navegador real** | Lo que un arnés jsdom no puede ver: render WebGL, layout, móvil, repintado en zoom con ratón, fugas de memoria en el bucle de 24 h |
| `VIC_33` | QA del `terraform apply` de `FIL_16`/`FIL_17` + re-congelación — **contra AWS real, solo lectura** | Mínimo privilegio de la política SSM, ausencia de secretos en claro, estado congelado real, cero drift colateral del `-target` |

## Fuentes técnicas (leer antes)

- PR #234 (`FIL_55`), PR #235 (docs), `tasks/FIL_55_*.md`.
- `doc/FIL-16-alertado-salud-pipeline.md`, `doc/FIL-17-secretos-runtime-ssm.md`.
- `PROGRESS.md` — entrada 2026-09-01.
- `viz/build_mapa_animado.py` (`_TEMPLATE` + `_html()`), `tests/test_mapa_animado.py`.
- `infra/terraform/observabilidad.tf`, `lambda.tf`, `glue_scheduling.tf`.
- `infra/OPERACION.md`, `.claude/projects/.../memory/madrono-access.md` (cómo se llega a AWS).
