---
id: 39
slug: redesplegar-hora-madrid
title: "Redesplegar las Lambdas con los timestamps en hora de Madrid"
status: pending
force: false
allow_infra_apply: true
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-15T09:49:55+00:00"
updated_at: "2026-08-15T09:49:55+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

Las tareas 034-038 corrigieron el código de `ingesta/` para usar hora de Madrid.
Igual que la tarea 031 (que corrigió el empaquetado), un cambio de código en
`ingesta/` no llega solo a producción: el `.zip` de las 14 Lambdas está fijado al
`source_code_hash` de cuando se generó. Esta tarea reconstruye el paquete y
reaplica.

**`force: false` deliberado**: a partir de este `apply`, las 14 Lambdas (las que ya
funcionan) empiezan a escribir con el nuevo formato de timestamp en producción de
forma continua. Igual que en las tareas 030/033, prefiero que un humano revise la
verificación antes de fusionar.

**Excepción de alcance** (`allow_infra_apply: true`): permiso para `terraform
apply` sobre el `.zip` reconstruido (actualiza las 14 funciones in-place, mismo
mecanismo que la tarea 031) y para invocar Lambdas manualmente.

## Objetivo

Reaplicar el código actualizado y confirmar con invocaciones reales que los nuevos
objetos en Bronze usan hora de Madrid (offset `+01:00`/`+02:00` según DST, no
`+00:00`).

## Alcance concreto

1. `terraform plan`: confirma que el único cambio es el `source_code_hash`/
   `filename` de las 14 `aws_lambda_function` (in-place, sin recrear ni destruir
   nada) — mismo patrón que la tarea 031.
2. `terraform apply -auto-approve`.
3. Invoca manualmente al menos las 7 funciones ya confirmadas funcionando en
   producción (tráfico, EMT, BiciMAD, aparcamientos, calidad del aire,
   meteorología, cartelera de cines — ver `doc/033-conectar-lambda-layer-verificar.md`)
   y comprueba en el objeto escrito en Bronze que `ingested_at`/`measured_at`
   tienen offset de hora de Madrid, no `+00:00`.
4. Documenta en `doc/039-redesplegar-hora-madrid.md` el antes/después de al menos
   un ejemplo real de cada función invocada.

## Restricciones

- NO modifiques ningún fichero `.tf` en esta tarea (el código ya cambió en
  034-038, aquí solo se reempaqueta y aplica).
- NO ejecutes `terraform destroy`.
- Si alguna función que antes funcionaba dejara de hacerlo tras este redespliegue,
  documenta el error exacto — no intentes depurarlo ni arreglarlo aquí, sería una
  tarea de seguimiento.

## Criterios de aceptación

- Las 14 funciones actualizadas in-place, sin recrear ni destruir nada.
- Al menos las 7 funciones ya verificadas antes siguen escribiendo en Bronze, ahora
  con timestamps en hora de Madrid, confirmado con invocaciones reales.
- `doc/039-redesplegar-hora-madrid.md` documenta el antes/después.
