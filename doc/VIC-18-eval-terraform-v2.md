# VIC-18 — Evaluación técnica ronda 2: Terraform, plan completo

Ejecutado 30/8. Solo `plan`/`validate`, ningún `apply`.

## Verificado

- `terraform validate` → limpio.
- `terraform fmt -check -diff` → limpio.
- `terraform plan` agregado (`-target` desde `terraform state list`,
  Kafka excluido, 335 recursos objetivo — mismo criterio que `VIC_13`):
  **`2 to add, 54 to change, 0 to destroy`**. Sin errores.
- Los "2 to add" son `aws_iam_policy.ingestion_lambda_secrets` +
  `aws_iam_role_policy_attachment.ingestion_lambda_secrets` (`FIL_17`),
  y "16 to change" dentro de esos 54 son las 16 `aws_lambda_function.producer`
  que pasarían de variables de entorno en claro a `_SSM_PATH`.
- Sin `Resource: "*"` en ninguna política IAM del árbol completo.

## Hallazgo importante — `FIL_17` no está aplicado en AWS real todavía

**Esto es más urgente que el estado "sin aplicar" de `FIL_16`.**
`FIL_16` (alertado) es seguro de dejar sin aplicar durante la congelación
— no hay nada que alertar con la ingesta parada. `FIL_17` es una
**corrección de seguridad**: mientras no se aplique, las 16 funciones
Lambda de productores en la cuenta real de AWS **siguen teniendo sus
credenciales (`AEMET_API_KEY`, `EMT_CLIENT_ID`, etc.) como variables de
entorno en claro**, visibles vía `aws lambda get-function-configuration`
— exactamente el problema que `FIL_17` se escribió para resolver. El
código y los tests están listos; el `terraform apply` no se ha ejecutado.

No se aplica aquí (fuera de alcance de este ticket — solo `plan`), pero se
marca como hallazgo de prioridad alta para quien tenga permiso de aplicar
infraestructura: **aplicar `FIL_17` no depende de reanudar la ingesta**,
es una corrección de seguridad independiente y se puede (¿debería?)
aplicar aunque el pipeline siga congelado.

## Hallazgo menor — 2 variables de Terraform sin usar

`variables.tf` declara `lambda_default_timeout_seconds` (default 60) y
`lambda_default_memory_mb` (default 256) con una descripción que dice
"se puede sobrescribir por productor en `local.producers`" — implica que
son un valor por defecto con fallback. **Verificado que no es así**:
`lambda.tf::local.producers` tiene las 16 entradas con `timeout`/
`memory_mb` **hardcodeados explícitamente** cada una (muchas coinciden
con 60/256 por coincidencia, no por referenciar la variable). Ninguna
entrada usa `var.lambda_default_timeout_seconds`/`var.lambda_default_memory_mb`
— confirmado con `grep -rn` sobre todo el árbol `.tf`. Son variables
muertas con una documentación que promete un comportamiento que el código
no tiene.

## Recomendación

- **Prioridad alta**: aplicar `FIL_17` (`terraform apply -target=...`,
  pasos ya documentados en `doc/FIL-17-...md`) independientemente de si
  se reanuda la ingesta — es una corrección de seguridad, no un cambio de
  datos.
- **Prioridad baja**: decidir en `variables.tf` si `lambda_default_timeout_seconds`/
  `lambda_default_memory_mb` se conectan de verdad (p. ej.
  `coalesce(each.value.timeout, var.lambda_default_timeout_seconds)`) o se
  eliminan si `local.producers` seguirá siendo siempre explícito por
  diseño.

Ambos, si se actúa sobre ellos, requieren un ticket `FIL_*` — no se
aplica nada en este ticket.
