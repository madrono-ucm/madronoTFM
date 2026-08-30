# VIC-20 — Evaluación técnica ronda 2: consistencia cruzada de documentación

Ejecutado 30/8.

## Verificado, sin contradicciones

- Conteo de tools (9): consistente entre `README.md` raíz (única mención
  fuera de tasks/doc históricos) — sin contradicción en otros README.
- Conteo de productores (16 continuos / 7 batch / 1 retirado): solo en
  `README.md` raíz, auto-consistente.
- Mención de la congelación del pipeline: presente en `README.md` raíz,
  `asistente/README.md`, `infra/OPERACION.md`. Ausente en
  `modelado/README.md` (aceptable, es un doc de metodología ML, no de
  estado operativo) y `doc/README.md` (aceptable, es el índice de la
  bitácora, no describe estado).
- Enlaces internos (`[texto](ruta.md)`) en `README.md`, `asistente/README.md`,
  `modelado/README.md`: sin roturas.
- Referencias `doc/*.md` desde cualquier `tasks/*.md`: sin roturas (148
  ficheros en `doc/`, todas las referencias resuelven).

## Hallazgo — ticket nuevo, no trivial

`asistente/README.md`, sección "Las 6 `tools`" (línea 250): tabla
gravemente desactualizada, 3 de 6 filas marcadas `NotImplementedError`
para tools que llevan tiempo implementadas de verdad, y le faltan las 3
tools `*_prevista`. No es un fix de una cifra o un enlace — reescribir la
tabla completa está fuera del criterio de "trivial" de este ticket →
[`FIL_29`](../tasks/FIL_29_asistente-readme-tabla-6-tools-obsoleta.md).

## Sin más hallazgos

El resto de la documentación de nivel superior (`README.md`,
`infra/OPERACION.md`, `doc/README.md`) está consistente entre sí tras las
correcciones ya aplicadas por `FIL_19`/`FIL_25`.
