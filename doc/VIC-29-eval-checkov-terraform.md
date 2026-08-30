# VIC_29 — seguridad de IaC con checkov sobre Terraform (ronda 5)

**Fecha:** 2026-08-30. `checkov` no estaba instalado — primera vez que
corre sobre `infra/terraform/`. Solo lectura, no toca ningún recurso real
ni corre `plan`/`apply`.

## Comando

```
checkov -d infra/terraform/
```

**260 hallazgos `FAILED`**, ninguno `CKV2` de severidad crítica en control
de acceso (sin bucket público, sin puerto SSH abierto a `0.0.0.0/0`).
Desglose por check (top):

| Check | Nº | Qué pide |
|---|---|---|
| `CKV_AWS_195` | 48 | Glue con `SecurityConfiguration` asociada |
| `CKV_AWS_338`/`158` | 33+33 | CloudWatch Logs: retención ≥1 año / cifrado KMS |
| `CKV_AWS_297` | 23 | EventBridge Scheduler con CMK |
| `CKV_AWS_50/272/173/117/116/115` | 16 c/u | Lambda: X-Ray, code-signing, cifrado de env vars, VPC, DLQ, límite de concurrencia |
| `CKV_AWS_337` | 6 | SSM parameters con CMK |
| resto (S3, EC2, SG) | ~15 | ver detalle abajo |

## Triaje

**Los primeros ~230 (Glue/CloudWatch/Scheduler/Lambda/SSM con CMK, X-Ray,
VPC, DLQ, code-signing, límite de concurrencia)**: son, sin excepción,
controles de nivel *enterprise-compliance* (cifrado con clave gestionada
por el cliente en vez de la clave por defecto de AWS, trazado distribuido,
firma de código, aislamiento de red) que no encajan con un proyecto de TFM
de **coste 0** con datos públicos no sensibles (datasets abiertos de
datos.madrid.es) — el propio proyecto ya documenta en varios sitios
(`infra/OPERACION.md`, discutido en rondas anteriores) que la prioridad es
coste cero, no cumplimiento normativo de nivel producción. Añadir CMKs a
~150 recursos, DLQ + VPC a 16 Lambdas, etc. tendría coste real de AWS y
complejidad operativa sin beneficio de seguridad proporcional para este
caso de uso. **No amerita `FIL_*`**: son la definición de "regla pensada
para un entorno que no es este", tal como anticipaba el alcance del
ticket.

**4 hallazgos sobre `aws_instance.kafka`/`aws_security_group.kafka`/
`kafka.tf`** (`CKV_AWS_88` IP pública, `CKV_AWS_79` IMDSv1, `CKV_AWS_382`
egress abierto, monitorización detallada): verificado contra
`infra/OPERACION.md` línea 8: *"Lo único deliberadamente sin aplicar es
Kafka (`kafka.tf`)"* — este código nunca ha creado un recurso real en AWS.
Los 4 hallazgos son sobre infraestructura que no existe hoy. **No amerita
`FIL_*` ahora** — si algún día se decide aplicar `kafka.tf`, revisar
`CKV_AWS_79` (IMDSv2, cambio de una línea, buena práctica real y barata)
antes del `apply`, pero no antes.

**Los 12 restantes, sobre buckets S3 reales y sí aplicados**
(`aws_s3_bucket.lakehouse`, `athena_results`, `build_artifacts`:
versionado, logging de acceso, replicación entre regiones, cifrado con
KMS en vez de AES256 por defecto, notificaciones de eventos): ninguno
implica un bucket público ni datos sin cifrar (el cifrado SSE-S3 por
defecto de AWS ya aplica; estos checks piden ir un paso más allá con
KMS-CMK). Replicación entre regiones es sobre-ingeniería de continuidad
de negocio para un lakehouse de TFM. Versionado y logging de acceso son
los dos con más mérito real (protección ante borrado accidental de una
partición, trazabilidad de acceso), pero de nuevo chocan con la prioridad
de coste 0 ya establecida explícitamente por el proyecto (versionado
duplica el coste de almacenamiento de todo lo que se sobrescriba).
**No amerita `FIL_*`** — es una decisión de producto (coste vs. robustez)
ya inclinada deliberadamente hacia el coste en todo el proyecto, no un
descuido de este código en particular.

## Conclusión

**Cero `FIL_*` nuevos de `VIC_29`.** Ningún hallazgo de `checkov`
representa una vulnerabilidad explotable hoy (nada público, nada sin
cifrar básico, nada con `kafka.tf` realmente desplegado). El volumen es
enteramente controles de cumplimiento de nivel empresarial que no encajan
con un proyecto de coste 0 — el propio criterio de aceptación del ticket
("una regla pensada para un entorno de producción crítico puede no
aplicar aquí") se cumple para prácticamente el 100% de los hallazgos.
