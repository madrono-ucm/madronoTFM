# 039 — Redesplegar las 14 Lambdas con los timestamps en hora de Madrid

## Qué se implementó

Las tareas 034-038 corrigieron el código de `ingesta/` para usar hora de Madrid en
todos los timestamps, pero (igual que la tarea 031 con el empaquetado) ese cambio de
código no llegaba solo a producción: el `.zip` de las 14 funciones Lambda estaba
fijado al `source_code_hash` de cuando se generó por última vez (tarea 033). Esta
tarea reconstruye el paquete a partir del `ingesta/` actual (rama `main` tras el
merge de la tarea 038) y reaplica sobre las 14 funciones ya existentes, sin tocar
ningún fichero `.tf`.

No se ha modificado ningún fichero `.tf`: el cambio de infraestructura es puramente
el contenido del `.zip` generado por `data.archive_file.ingesta_source`
(`infra/terraform/lambda.tf`), reconstruido automáticamente por Terraform a partir
del código fuente actual de `ingesta/`.

## `terraform.tfvars`/`backend.hcl` regenerados (no commiteados)

Mismo patrón que las tareas 029-033: se copiaron `backend.hcl.example` →
`backend.hcl` y `terraform.tfvars.example` → `terraform.tfvars`, añadiendo a este
último el ARN de la Lambda Layer ya publicada y conectada por las tareas 032/033
(`lambda_dependencies_layer_arn = "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1"`,
sin cambios respecto a la tarea 033). Ambos ficheros están en `.gitignore` y se
eliminaron del disco al terminar la tarea, junto con `.terraform/` y
`.terraform.lock.hcl`.

## `terraform plan` antes de aplicar

```
Plan: 0 to add, 15 to change, 0 to destroy.
```

Los 15 cambios, exactamente el patrón ya documentado en las tareas 031/033:
- Las **14** `aws_lambda_function.producer[*]` in-place, únicamente
  `source_code_hash`/`filename` (nuevos por el `.zip` reconstruido: el hash pasó de
  `oEk0ApHeBkEwPYGudoNl34GDzk7lDglAM5VhYafqY8k=`/`0wAxJpyDz1N4n9ZcMUJFw2wYtX6OBJl+CPmT9tVZCDA=`
  — según la función, dependiendo de si se había reempaquetado ya en algún `apply`
  intermedio — al mismo hash nuevo `e9Vx4zTc8Kp0sgJ4KPqs5+BgwTFmh2v67BPocVfFSV4=` en
  las 14). Ningún otro atributo cambió (27 atributos "unchanged" en cada una).
- `aws_iam_policy.scheduler_invoke_lambda` in-place — mismo efecto colateral ya
  documentado en las tareas 031/033 (la política depende de
  `[for fn in aws_lambda_function.producer : fn.arn]`, y Terraform no puede
  garantizar en fase de `plan` que los ARNs de funciones con cambios pendientes no
  cambien, aunque en la práctica un `update-function-code` nunca cambia el ARN).

Ningún `will be created` ni `will be destroyed` en el plan.

## `terraform apply`

```
terraform apply -var-file=terraform.tfvars -auto-approve
```

`Apply complete!` sin error. Un segundo `apply` inmediato confirmó
`Apply complete! Resources: 0 added, 0 changed, 0 destroyed.`: el estado converge,
sin drift residual.

Región: `eu-west-1`. Cuenta AWS: `222234418587`. No se creó ni se destruyó ningún
recurso — solo se actualizó in-place el código de las 14 funciones ya existentes
(mismos nombres, mismos ARNs) y, con contenido idéntico, la política IAM
`madrono-tfm-dev-scheduler-invoke-lambda`. Las 14 funciones quedaron con
`CodeSha256 = e9Vx4zTc8Kp0sgJ4KPqs5+BgwTFmh2v67BPocVfFSV4=` (verificado con
`aws lambda get-function-configuration`).

## Verificación: escrituras programadas ya usan hora de Madrid antes de invocar nada a mano

Nada más completar el `apply` (las 14 funciones ya tenían el nuevo código), se
comprobó el bucket Bronze y ya había un objeto nuevo de `transporte_publico_emt`
escrito por el `schedule` programado (`emt_llegadas`, cadencia de ~5 min), a las
17:01:55 UTC — apenas segundos después del `apply` (17:01:11 UTC según
`LastModified` de la función `trafico`):

```
transporte_publico_emt/fecha=2026-08-15/hora=19/20260815T190154_487b4efb.json
```

Dos señales de que ya es el código nuevo, sin necesidad de mirar el contenido:
- La partición es `hora=19` aunque el objeto se escribió a las 17:01 UTC (19:01 en
  Madrid, CEST = UTC+2) — antes de esta tarea particionaba en UTC.
- El nombre de fichero ya no lleva el sufijo `Z` (`20260815T190154_...`, no
  `20260815T190154Z_...`) — cambio de formato introducido por la tarea 034 al pasar
  el momento de partición/nombrado a hora de Madrid.

## Verificación con invocaciones manuales reales: antes/después

Se invocaron manualmente las 7 funciones ya confirmadas funcionando en producción
por la tarea 033 (`doc/033-conectar-lambda-layer-verificar.md`): tráfico, EMT,
BiciMAD, aparcamientos, calidad del aire, meteorología y cartelera de cines. Las 7
devolvieron `StatusCode: 200` y escribieron un objeto nuevo en Bronze.

| Función | Objeto **antes** del redespliegue (offset UTC) | Objeto **después** (invocación manual, offset Madrid) |
|---|---|---|
| `trafico` | `measured_at: 2026-08-15T15:50:15+00:00`<br>`ingested_at: 2026-08-15T15:56:26.204073+00:00` | `measured_at: 2026-08-15T18:55:14+02:00`<br>`ingested_at: 2026-08-15T19:03:46.425034+02:00` |
| `transporte_publico_emt` | `ingested_at: 2026-08-15T16:56:51.132140+00:00` | `ingested_at: 2026-08-15T19:04:14.386574+02:00` |
| `bicimad` | `measured_at: 2026-08-15T15:54:37+00:00`<br>`ingested_at: 2026-08-15T15:57:04.138023+00:00` | `measured_at: 2026-08-15T19:00:50+02:00`<br>`ingested_at: 2026-08-15T19:03:49.282543+02:00` |
| `aparcamientos` | `measured_at: 2026-08-15T16:59:37+00:00`<br>`ingested_at: 2026-08-15T17:01:38.269669+00:00` | `measured_at: 2026-08-15T19:00:48+02:00`<br>`ingested_at: 2026-08-15T19:03:51.978553+02:00` |
| `calidad_aire` | `measured_at: 2026-08-15T16:00:00+00:00`<br>`ingested_at: 2026-08-15T16:55:40.297361+00:00` | `measured_at: 2026-08-15T18:00:00+02:00`<br>`ingested_at: 2026-08-15T19:04:00.300424+02:00` |
| `meteorologia` | `measured_at: 2026-08-15T16:00:00+00:00`<br>`ingested_at: 2026-08-15T16:55:07.234012+00:00` | `measured_at: 2026-08-15T18:00:00+02:00`<br>`ingested_at: 2026-08-15T19:04:06.218536+02:00` |
| `cartelera_cines_estrenos` | `captured_at: 2026-08-15T06:00:04.766369+00:00` | `captured_at: 2026-08-15T19:04:11.249691+02:00` |

Los objetos "antes" son los últimos escritos por el `schedule` programado con el
código previo a esta tarea (o, en el caso de `cartelera_cines_estrenos`, la única
ejecución del día, a las 06:00). Los objetos "después" son el resultado directo de
`aws lambda invoke --function-name madrono-tfm-dev-<clave> --payload '{}'`
ejecutado tras el `apply`, con lectura completa del objeto JSON escrito en
`s3://madrono-tfm-dev-bronze-222234418587/`. Las 7 confirman offset `+02:00`
(Madrid en verano/CEST) en vez de `+00:00`, tal como pedía el criterio de
aceptación.

Ninguna de las 7 funciones dejó de funcionar tras el redespliegue: las 7 que ya
escribían en Bronze antes de esta tarea lo siguen haciendo, ahora con el offset
correcto.

## Restricciones respetadas

- **No se ha modificado ningún fichero `.tf`** — el único cambio de infraestructura
  es el contenido reempaquetado del `.zip` (generado automáticamente por
  `data.archive_file.ingesta_source` a partir del `ingesta/` ya corregido por las
  tareas 034-038).
- **No se ha ejecutado `terraform destroy`** en ningún momento.
- No se ha intentado depurar ni arreglar nada: las 7 funciones invocadas
  funcionaron correctamente a la primera, sin ningún fallo que documentar como
  regresión de este redespliegue.
- **No se ha dejado nada programado nuevo** (cron, systemd timer, bucle) en esta
  EC2: las invocaciones fueron puntuales (`aws lambda invoke` x7), y los
  `aws_scheduler_schedule` ya existentes desde las tareas 029/030 no se han tocado.
- `terraform.tfvars`, `backend.hcl`, `.terraform/` y `.terraform.lock.hcl` se
  regeneraron a partir de sus `.example` (gitignored, mismo patrón que las tareas
  029-033) y se eliminaron del disco al terminar la tarea.
- El alcance del `apply` se limitó exactamente a lo que describía el prompt de esta
  tarea: reempaquetar y reaplicar el código de las 14 funciones ya existentes
  in-place. No se creó ni se destruyó ningún recurso.

## `force: false` — por qué no se fusiona sola

Igual que en las tareas 030/033, este PR no se fusiona automáticamente: a partir de
este `apply`, las 14 funciones (incluidas las que ya escriben datos de producción
reales de forma continua vía sus `schedule`) empiezan a escribir con el nuevo
formato de timestamp de forma permanente. Conviene que un humano revise esta
verificación antes de fusionar, aunque fusionar en sí no cambia el estado de AWS
(el `apply` ya se ejecutó contra la cuenta real).

## Relevante para tareas futuras

- Con esta tarea se completa la cadena código→producción de las tareas 034-039: los
  14 productores de `ingesta/capturas/` escriben en Bronze con timestamps en hora
  de Madrid, tanto en el código fuente (034-038) como en las funciones Lambda
  desplegadas (039, esta tarea).
- Las 7 funciones restantes que la tarea 033 dejó **sin verificar explícitamente**
  con una invocación real (`ruido`, `afluencia_lugares`, `bluesky_menciones`,
  `agenda_eventos`, `aemet_prevision_avisos`, `cams_calidad_aire`,
  `aforos_peatones_bicicletas`) siguen en la misma situación tras esta tarea: no se
  han invocado manualmente aquí tampoco (el criterio de aceptación pedía "al menos
  las 7 ya confirmadas", no las 14) — de estas, 3 siguen bloqueadas por
  credenciales SSM placeholder (`afluencia_lugares`, `aemet_prevision_avisos`,
  `cams_calidad_aire`, ver tarea 033), y `aforos_peatones_bicicletas` sigue con el
  timeout ~120s en Lambda documentado por la tarea 033 (no reproducido en EC2,
  causa raíz sin confirmar) — ninguno de estos 4 bloqueos es nuevo de esta tarea.
- Si una tarea futura vuelve a cambiar código de `ingesta/`, recordar que hace
  falta repetir este mismo patrón (`terraform plan`/`apply` desde
  `infra/terraform/`) para que el cambio llegue a las Lambdas ya desplegadas: el
  `.zip` no se reconstruye solo al mergear a `main`, solo cuando alguien ejecuta
  Terraform.
