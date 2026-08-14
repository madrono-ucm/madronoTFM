# 033 — Conectar la Lambda Layer a las 14 funciones y verificar escritura real en Bronze

## Qué se implementó

Última pieza de la migración a producción de la ingesta: se conectó la Lambda Layer
de dependencias de terceros publicada por la tarea 032
(`arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1`)
a las 14 funciones Lambda de productores, y se verificó con invocaciones manuales
reales que el pipeline completo (import de `ingesta/` + dependencias de terceros +
`BronzeWriter`) escribe datos de verdad en el bucket Bronze.

**Cambio de código**: un solo valor en `terraform.tfvars`
(`lambda_dependencies_layer_arn = "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1"`),
sin tocar ningún fichero `.tf`. Además se corrigió una descripción de output que
había quedado obsoleta: `outputs.tf` (`lambda_dependencies_layer_arn`) decía
"Todavía NO conectada... eso es la tarea 033", que ya no era cierto tras esta
tarea — se actualizó el texto para reflejar el estado real (conectada por esta
tarea). No se ha tocado el código de `ingesta/`.

## `terraform plan` antes de aplicar

```
Plan: 0 to add, 15 to change, 0 to destroy.
```

Los 15 cambios fueron exactamente los esperados según lo que ya anticipaba
`doc/031-arreglo-empaquetado-lambda.md` para un cambio de este tipo:
- Las **14** `aws_lambda_function.producer[*]` in-place, únicamente
  `+ layers = ["arn:...:layer:madrono-tfm-dev-ingesta-dependencies:1"]` (0 →1
  elemento). Ningún otro atributo cambió (28 atributos "unchanged" en cada una).
- `aws_iam_policy.scheduler_invoke_lambda` in-place — mismo efecto colateral ya
  documentado en la tarea 031: como las 14 funciones tienen un cambio pendiente,
  Terraform no puede garantizar en fase de `plan` que sus ARNs no cambien, así que
  recalcula la política que depende de `[for fn in aws_lambda_function.producer :
  fn.arn]`. Confirmado tras el `apply` que el contenido no cambió realmente (los
  ARNs de funciones Lambda existentes no cambian al añadir una layer).

Ningún `will be created` ni `will be destroyed` en el plan. Se procedió a aplicar
tal como pedía el criterio de aceptación.

## `terraform apply`

```
terraform apply -var-file=terraform.tfvars -auto-approve
```

`Apply complete!` sin error. Un segundo `apply` inmediato confirmó
`Apply complete! Resources: 0 added, 0 changed, 0 destroyed.`: el estado converge,
sin drift residual respecto al primer `apply`.

Región: `eu-west-1`. Cuenta AWS: `222234418587`. No se creó ni se destruyó ningún
recurso — solo se actualizaron in-place las 14 funciones ya existentes (mismos
nombres, mismos ARNs) y, con contenido idéntico, la política IAM del scheduler.

## Verificación: las 14 funciones tienen la Layer adjunta

`aws lambda get-function-configuration --function-name madrono-tfm-dev-<clave>
--query 'Layers[0].Arn'` en las 14 funciones → las 14 devuelven
`arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1`.

(Nota operativa: el AWS CLI de esta EC2 no tiene una región por defecto
configurada — sin `--region`/`AWS_DEFAULT_REGION` explícito, los comandos caían en
`eu-south-2` y devolvían `ResourceNotFoundException`. Todos los comandos de esta
tarea se ejecutaron con `AWS_DEFAULT_REGION=eu-west-1` explícito.)

## Verificación: invocaciones manuales reales y escritura en Bronze

Se invocaron manualmente (`aws lambda invoke`) 6 funciones de naturaleza distinta.
Resultado, función por función:

| Función | Resultado | Detalle |
|---|---|---|
| `bicimad` | **Éxito** | `{"dataset": "bicimad", "records_written": 681, "location": "s3://madrono-tfm-dev-bronze-222234418587/bicimad/fecha=2026-08-14/hora=22/20260814T221134Z_5b55bd44.json"}`. Sin `secret_env`. |
| `cartelera_cines_estrenos` | **Éxito** | `{"dataset": "cartelera_cines_estrenos", "records_written": 6, "location": ".../cartelera_cines_estrenos/.../20260814T221134Z_d584ea30.json"}`. Usa `beautifulsoup4` (de la Layer) para parsear HTML — confirma que la Layer sirve dependencias más allá de `requests`. Sin `secret_env`. |
| `trafico` | **Éxito** | `{"dataset": "trafico", "location": ".../trafico/.../20260814T221306Z_581f836b.json"}` (2.5 MB, el dataset más pesado de los probados). Sin `secret_env`. |
| `calidad_aire` | **Éxito** | `{"dataset": "calidad_aire", "records_written": 123, "location": ".../calidad_aire/.../20260814T221309Z_1720e241.json"}`. Sin `secret_env`. |
| `transporte_publico_emt` | **Falla (bloqueo ya conocido, no de esta tarea)** | `RuntimeError: No se pudo completar la petición a la API EMT tras 3 intentos` — el código llega hasta `fetch_access_token` (pasa el `import`, pasa la Layer) y falla al autenticar. Causa: `EMT_CLIENT_ID`/`EMT_PASS_KEY` siguen con el valor placeholder `CHANGEME-SET-MANUALLY-OUTSIDE-TERRAFORM` en SSM (pendiente desde las tareas 018/019/029/030/031, fuera de alcance de esta tarea fijarlos). |
| `aforos_peatones_bicicletas` | **Falla (timeout, no relacionado con la Layer)** | Invocada 2 veces (una con `--cli-read-timeout 120` que expiró en el cliente, repetida con `--cli-read-timeout 300`); **ambas** terminaron con `Sandbox.Timedout` / `REPORT ... Status: timeout` a los 120.00s exactos (el `timeout` configurado en `local.producers.aforos_peatones_bicicletas`). En ambos casos el log muestra solo un `WARNING` inicial ("Hay un recurso de peatones más reciente que el configurado...") y ningún otro evento hasta el timeout — el proceso se cuelga en algún punto posterior a ese warning (muy probablemente una descarga de red lenta/bloqueante del CSV de datos.madrid.es, sin que el código tenga un timeout de `requests` explícito) durante ~2 minutos sin producir ni error ni resultado. **No se ha modificado el código de `ingesta/`** para investigar ni arreglar esto, conforme a las restricciones de esta tarea — queda documentado como una tarea de seguimiento (ver abajo). |

**Confirmación de escritura real y nueva en Bronze** (`aws s3 ls
s3://madrono-tfm-dev-bronze-222234418587/ --recursive`, antes y después de las
invocaciones):

```
2026-08-14 22:08:09     355758 bicimad/fecha=2026-08-14/hora=22/20260814T220808Z_7ecf8e4a.json
2026-08-14 22:11:36     355753 bicimad/fecha=2026-08-14/hora=22/20260814T221134Z_5b55bd44.json
2026-08-14 22:12:05     355749 bicimad/fecha=2026-08-14/hora=22/20260814T221204Z_21542393.json
2026-08-14 22:13:10      56927 calidad_aire/fecha=2026-08-14/hora=22/20260814T221309Z_1720e241.json
2026-08-14 22:11:35       2006 cartelera_cines_estrenos/fecha=2026-08-14/hora=22/20260814T221134Z_d584ea30.json
2026-08-14 22:09:28    2526915 trafico/fecha=2026-08-14/hora=22/20260814T220924Z_239bc7eb.json
2026-08-14 22:11:28    2527052 trafico/fecha=2026-08-14/hora=22/20260814T221126Z_47b9ee99.json
2026-08-14 22:13:08    2527052 trafico/fecha=2026-08-14/hora=22/20260814T221306Z_581f836b.json
```

El bucket estaba vacío excepto un objeto (`bicimad/.../20260814T220808Z_...json`,
ver nota abajo) antes de empezar las invocaciones manuales. Cada invocación exitosa
produjo exactamente un objeto nuevo, en el prefijo `<dataset>/fecha=.../hora=.../`
esperado (partición por fecha/hora, formato ya establecido por `BronzeWriter` en
tareas anteriores).

**Nota — las 20 invocaciones programadas ya están escribiendo solas**: se observan
objetos de `bicimad` y `trafico` con timestamps que **no** corresponden a ninguna
invocación manual de esta tarea (`20260814T220808Z`, `20260814T221204Z` para
bicimad; `20260814T220924Z`, `20260814T221126Z` para trafico) — son las primeras
ejecuciones reales de los `aws_scheduler_schedule` de la tarea 029/030, disparadas
automáticamente cada pocos minutos según su cadencia, ya con la Layer conectada.
Esto confirma, de forma independiente a las invocaciones manuales de esta tarea,
que el pipeline programado end-to-end (EventBridge Scheduler → Lambda → Layer →
`ingesta/` → Bronze) funciona en producción real desde el momento del `apply` de
esta tarea — exactamente el "punto real de arranque de la producción de datos"
que motivaba el `force: false` de esta tarea.

## Funciones no invocadas en esta tarea (ni éxito ni fallo confirmado)

Las 8 funciones restantes no se invocaron manualmente (el criterio de aceptación
pedía 2-3 invocaciones; se hicieron 6, cubriendo ya los tres perfiles pedidos —
simple, con dependencia de parsing HTML, con credenciales reales — y confirmando
además, vía las escrituras programadas observadas, que el pipeline funciona de
forma continua). Quedan **sin verificar explícitamente en esta tarea** (no se
sabe si fallarían o no):

`aparcamientos`, `meteorologia`, `ruido`, `afluencia_lugares`,
`bluesky_menciones`, `agenda_eventos`, `aemet_prevision_avisos`,
`cams_calidad_aire`.

De estas, `afluencia_lugares` (`GOOGLE_MAPS_API_KEY`), `aemet_prevision_avisos`
(`AEMET_API_KEY`) y `cams_calidad_aire` (`CAMS_ADS_API_KEY`) usan parámetros SSM
que también siguen en el mismo placeholder que bloquea `transporte_publico_emt` —
es esperable (no confirmado) que fallen por el mismo motivo hasta que alguien fije
esas 3 credenciales a mano. Las otras 5 (`aparcamientos`, `meteorologia`, `ruido`,
`bluesky_menciones`, `agenda_eventos`) no usan secretos y, por el mismo patrón que
`bicimad`/`trafico`/`calidad_aire`/`cartelera_cines_estrenos`, es razonable esperar
que funcionen — pero no se ha confirmado con una invocación real en esta tarea.

## Restricciones respetadas

- **No se ha ejecutado `terraform destroy`** en ningún momento.
- **No se ha modificado el código de `ingesta/`**, ni para arreglar el timeout de
  `aforos_peatones_bicicletas` ni por ningún otro motivo — se documenta el
  problema, tal como pedía el enunciado, en vez de intentar resolverlo.
- El único cambio de código es el valor de `lambda_dependencies_layer_arn` en
  `terraform.tfvars` (no commiteado, regenerado desde `.example`, ver abajo) y la
  descripción de un output obsoleto en `outputs.tf` (commiteado).
- **No se ha dejado nada programado nuevo** (cron, systemd timer, bucle) en esta
  EC2: los 20 `aws_scheduler_schedule` ya estaban `ENABLED` desde la tarea 030, sin
  cambios en esta tarea a su definición ni cadencia.
- `terraform.tfvars`, `backend.hcl`, `.terraform/` y `.terraform.lock.hcl` se
  regeneraron a partir de sus `.example` (gitignored, mismo patrón que las tareas
  029-032) y se han eliminado del disco al terminar la tarea.

## `force: false` — por qué no se fusiona sola

Igual que en la tarea 030, este PR no se fusiona automáticamente: a partir de este
`apply`, los 20 schedules ya disparan invocaciones reales con la Layer conectada, y
las funciones sin bloqueo de credenciales (confirmado: `bicimad`, `trafico`,
`calidad_aire`, `cartelera_cines_estrenos`; probable pero no confirmado: las otras
5 sin `secret_env`) están escribiendo datos de producción reales en Bronze de forma
continua, sin intervención humana adicional. Conviene que un humano revise este
documento — en particular la lista de funciones no verificadas y el timeout de
`aforos_peatones_bicicletas` — antes de fusionar, aunque fusionar en sí no cambia
el estado de AWS (el `apply` ya se ejecutó contra la cuenta real).

## Relevante para tareas futuras

- **Bloqueante de seguimiento, no arreglado aquí**: `aforos_peatones_bicicletas`
  (schedule mensual, día 1 a las 06:00 Europe/Madrid — próxima ejecución real
  lejana, no urgente) se cuelga ~120s tras un WARNING sobre un recurso CSV más
  reciente disponible que el configurado en el código, y expira por timeout sin
  error explícito. Antes del próximo disparo programado (día 1 del mes que viene)
  convendría investigar `ingesta/capturas/aforos_peatones_bicicletas_madrid.py`:
  candidatos más probables son (a) una descarga sin `timeout=` explícito en la
  llamada a `requests` que se cuelga contra `datos.madrid.es`, o (b) el propio
  `timeout = 120` de `local.producers.aforos_peatones_bicicletas` en
  `infra/terraform/lambda.tf` siendo insuficiente para el tamaño real del CSV en
  producción (funcionaría en local con datos de prueba más pequeños/mockeados,
  pero no contra el endpoint real) — en ambos casos requiere decidir entre tocar
  el código (más robusto: timeout explícito + reintentos acotados) o solo subir
  `timeout`/`memory_mb` en Terraform (más simple, pero no soluciona una causa raíz
  de red lenta si la hubiera).
- **Sigue pendiente, sin cambios en esta tarea**: fijar los 5 parámetros SSM reales
  (`terraform output secret_ssm_parameter_names`) a mano fuera de Terraform. Sin
  eso, `transporte_publico_emt` (confirmado fallando) y, con alta probabilidad,
  `afluencia_lugares`/`aemet_prevision_avisos`/`cams_calidad_aire` (no confirmado,
  mismo patrón de credencial placeholder) seguirán fallando en cada disparo
  programado.
- **Recomendable, no bloqueante**: invocar manualmente las 5 funciones sin
  `secret_env` que no se probaron en esta tarea (`aparcamientos`, `meteorologia`,
  `ruido`, `bluesky_menciones`, `agenda_eventos`) para completar la verificación
  end-to-end de las 14, o simplemente esperar y comprobar sus primeras escrituras
  programadas en Bronze (cadencias ya definidas en `local.schedules`, todas se
  disparan dentro de las próximas 24h salvo `aforos_peatones_bicicletas`, que es
  mensual).
- Con esto se completa la cadena descrita por las tareas 026-033: captura de datos
  → paquete de código (031) → Layer de dependencias (032) → conexión (033) →
  escritura confirmada en Bronze. La ingesta de al menos 4 de los 14 datasets
  (`bicimad`, `trafico`, `calidad_aire`, `cartelera_cines_estrenos`) está
  operativa en producción real de extremo a extremo a partir de esta tarea.
