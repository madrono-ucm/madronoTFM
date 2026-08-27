---
id: 100
slug: normalizar-eol-terraform-file-hash
title: "QA: la tarea 098 no reconcilió el drift de Terraform — son finales de línea CRLF, no un apply incompleto"
status: pending
force: false
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-27T19:10:00+00:00"
updated_at: "2026-08-27T19:10:00+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Hallazgo de QA (auditoría de la tarea 098, verificado en vivo)

`doc/098-...md` afirma que, tras su `terraform apply`, un `terraform plan`
posterior confirmaba el estado deseado: **`5 to add, 0 to change, 0 to
destroy`** (solo Kafka pendiente, deliberadamente sin aplicar).

Ejecutado hoy (27/8) desde esta EC2 (rol `madrono-terraform-deployerEC2`,
el mismo que la propia tarea 098 dice que ya tenía los permisos correctos):

```
Plan: 55 to add, 64 to change, 50 to destroy.
```

**Casi idéntico al plan "roto" que la propia tarea 098 describe haber
corregido** (55/65/50). A primera vista esto parece que el `apply` nunca
se reconcilió de verdad, o que volvió a driftar de inmediato. Investigado a
fondo antes de asumir nada:

1. El fichero de estado remoto (`s3://madrono-tfm-terraform-state/infra/lakehouse/terraform.tfstate`)
   sí se escribió durante la ventana del `apply` (tres versiones seguidas a
   las 17:20-17:21 UTC del 26/8) — el `apply` sí persistió en el backend
   compartido, no es un problema de estado no guardado.
2. El objeto S3 realmente desplegado para, p. ej.,
   `aws_s3_object.glue_script_cartelera_cines_estrenos_silver_to_gold`
   (`glue-scripts/cartelera_cines_estrenos_silver_to_gold-aa6c09b63c18f746da024c09a020b01f.py`,
   subido a las 17:19:40 del 26/8) **coincide exactamente con el `etag` que
   Terraform tiene en `state`** — o sea, lo desplegado y lo que Terraform
   cree haber desplegado están de acuerdo entre sí.
3. Pero el contenido de ese objeto desplegado, comparado byte a byte contra
   el fichero real en `main`
   (`procesamiento/silver_gold/cartelera_cines_estrenos/glue_silver_to_gold.py`),
   **difiere únicamente en los finales de línea**: el objeto desplegado usa
   `CRLF` (`\r\n`), el checkout de esta EC2 usa `LF` (`\n`). Verificado con
   `tr -d '\r'` sobre el objeto desplegado → resultado **byte-a-byte
   idéntico** al fichero de `main`. Ninguna diferencia de lógica: el fix
   real del bug de `fecha` (tarea 090) **sí está desplegado correctamente**,
   solo con finales de línea distintos.
4. Repetido el mismo contraste para los otros 3 scripts que la tarea 090
   arregló (`agenda_eventos`, `bluesky_menciones`,
   `aforos_peatones_bicicletas`, todos `silver_to_gold`) — los 4 aparecen
   en el plan como "must be replaced", consistente con la misma causa.

## Causa raíz

El repositorio no tiene `.gitattributes` (`eol`/`text` sin especificar para
ningún fichero). Quien ejecutó el `terraform apply` real de la tarea 098 lo
hizo desde un entorno cuyo checkout de git normaliza a `CRLF` (Windows, o
`core.autocrlf=true`/`input` mal configurado) — así que el `file()`/`filemd5()`
de Terraform, al leer esos ficheros en ese entorno, calculó hashes sobre
contenido `CRLF` y los subió así a S3. Cualquier `terraform plan` posterior
ejecutado desde un checkout `LF` (esta EC2, casi seguro también el entorno
del propio demonio `madrono-agent`) calculará un hash distinto para el
mismo fichero — **drift perpetuo y falso**, no una regresión real ni un
`apply` incompleto.

**Riesgo si no se corrige**: si una futura tarea automatizada (o una
sesión humana) ve este plan y decide "reconciliar" el drift aplicándolo de
nuevo desde un checkout `LF`, invertiría el problema — dejaría los objetos
en `LF` y entonces sería el entorno `CRLF` original el que volvería a ver
drift en su próximo `plan`. Sin fijar la causa raíz, esto puede repetirse
indefinidamente entre entornos, y cada "reconciliación" mal informada
implicaría un `apply` real innecesario (aunque, verificado aquí, sin
impacto funcional).

## Objetivo

Fijar los finales de línea del repositorio para que cualquier checkout
(Linux o Windows) produzca el mismo contenido byte-a-byte, y hacer una
única reconciliación final desde un checkout así normalizado.

## Alcance concreto

1. Añade un `.gitattributes` en la raíz del repositorio forzando `LF` para
   el código fuente (como mínimo `*.py text eol=lf`, `*.tf text eol=lf`,
   `*.sh text eol=lf`; puedes usar `* text=auto eol=lf` si prefieres un
   criterio más amplio, pero documenta la elección).
2. Renormaliza el repositorio (`git add --renormalize .`) y confirma que el
   único cambio real son finales de línea (revisa el diff, no debe haber
   ningún cambio de contenido/lógica).
3. Tras fusionar el `.gitattributes`, desde un checkout ya normalizado (esta
   EC2 vale), vuelve a ejecutar `terraform plan` sin acotar y confirma que
   los ~50 "must be replaced" desaparecen y el plan vuelve a
   `5 to add, 0 to change, 0 to destroy` (solo Kafka).
4. Si tras el paso 3 sigue habiendo objetos S3 desplegados con `CRLF`
   (porque `.gitattributes` no reescribe lo ya desplegado, solo el
   checkout futuro), pide confirmación explícita al usuario antes de un
   `terraform apply` real que los reemplace por la versión `LF` — es una
   sola vez, de bajo riesgo (contenido idéntico salvo finales de línea,
   verificado en el punto 3 de "Hallazgo" arriba), pero sigue el mismo
   protocolo de aprobación que la tarea 098.
5. Documenta en `doc/100-...md` el hallazgo completo (ya verificado en este
   ticket) y el resultado de la normalización.

## Restricciones

- `allow_infra_apply: false` para el diagnóstico y el `.gitattributes`; si
  hace falta un `terraform apply` final (paso 4), sigue el patrón de dos
  tareas de `tasks/README.md` — no lo hagas dentro de esta misma tarea sin
  aprobación explícita.
- No toques la lógica de ningún script de `procesamiento/`/`ingesta/` — el
  contenido ya es correcto, esto es puramente finales de línea.
- No reescribas `doc/098-...md` — añade una nota "Actualización 27/8" al
  final señalando que el "drift" que parecía persistir tras esa tarea era
  CRLF/LF, no un `apply` incompleto (la tarea 098 sí cumplió su objetivo
  funcional: los 4 scripts de la tarea 090 y el resto están correctamente
  desplegados en cuanto a contenido).

## Criterios de aceptación

- `.gitattributes` fusionado, forzando `LF` para el código fuente.
- `terraform plan` sin acotar, desde un checkout normalizado, vuelve a dar
  `5 to add, 0 to change, 0 to destroy`.
- `doc/100-...md` documenta el hallazgo y la corrección.
- Hay un commit real.
