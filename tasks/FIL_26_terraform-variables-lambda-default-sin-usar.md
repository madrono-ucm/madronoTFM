---
kind: fil
title: "variables.tf: lambda_default_timeout_seconds/lambda_default_memory_mb declaradas pero sin ninguna referencia real"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-08-30"
---

> **Contexto**: encontrado en `VIC_18` (evaluación técnica ronda 2,
> `doc/PLAN-EVALUACION-TECNICA-2.md`), haciendo un `terraform plan`
> agregado de todo el árbol.

## Qué está impreciso (verificado)

`infra/terraform/variables.tf` declara:

```hcl
variable "lambda_default_timeout_seconds" {
  description = "Timeout por defecto (segundos) de cada función Lambda de
  productor. Se puede sobrescribir por productor en `local.producers`..."
  default = 60
}
variable "lambda_default_memory_mb" {
  description = "Memoria por defecto (MB) de cada función Lambda de
  productor. Se puede sobrescribir por productor en `local.producers`."
  default = 256
}
```

La descripción implica un valor por defecto con posibilidad de
sobrescritura por productor. **Verificado que no hay tal fallback**:
`grep -rn "lambda_default_timeout_seconds\|lambda_default_memory_mb"
--include="*.tf" .` solo encuentra la propia declaración en
`variables.tf` — cero referencias (`var.lambda_default_timeout_seconds`/
`var.lambda_default_memory_mb`) en `lambda.tf` ni en ningún otro fichero.
Las 16 entradas de `local.producers` tienen `timeout`/`memory_mb`
**hardcodeados explícitamente** cada una (varias coinciden con 60/256 por
coincidencia de valores, no por referenciar la variable).

## Por qué importa

Menor, pero real: alguien que lea `variables.tf` esperaría poder cambiar
el timeout/memoria por defecto de todos los productores sin tocar
`local.producers`, y ese cambio no tendría ningún efecto — las variables
están completamente desconectadas del recurso real.

## Qué hacer (propuesto, no aplicado aquí)

Dos opciones igual de válidas, a decidir:

1. Conectarlas de verdad: en `lambda.tf`,
   `timeout = coalesce(each.value.timeout, var.lambda_default_timeout_seconds)`
   (y equivalente para memoria), quitando el valor hardcodeado de las
   entradas de `local.producers` que coincidan con el default.
2. Eliminarlas de `variables.tf` si `local.producers` seguirá siendo
   siempre explícito por diseño (menos indirección, un solo sitio de
   verdad).

## Restricciones

- No se ha tocado ningún `.tf` en este ticket — solo verificación
  (`terraform plan` agregado + `grep` sobre el árbol completo).

## Criterios de aceptación

- `variables.tf` y `lambda.tf` consistentes entre sí (o las variables
  conectadas de verdad, o eliminadas).
