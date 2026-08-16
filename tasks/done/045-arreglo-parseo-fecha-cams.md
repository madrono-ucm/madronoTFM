---
id: 45
slug: arreglo-parseo-fecha-cams
title: Arreglar el parseo de fechas NetCDF de CAMS (ValueError en producción real)
status: done
force: true
allow_infra_apply: true
branch: task/045-arreglo-parseo-fecha-cams
pr_number: 92
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/92
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-15T10:25:00+00:00'
updated_at: '2026-08-16T00:29:18.096709+00:00'
started_at: '2026-08-16T00:11:27.719437+00:00'
submitted_at: '2026-08-16T00:28:11.832532+00:00'
merged_at: '2026-08-16T00:28:15Z'
---

## Contexto

El usuario ya obtuvo credenciales reales de Copernicus ADS (ver tarea 019/
`doc/019-captura-cams-calidad-aire-prevista.md`) y aceptó las licencias del
dataset `cams-europe-air-quality-forecasts` en
`https://ads.atmosphere.copernicus.eu/datasets/cams-europe-air-quality-forecasts?tab=download#manage-licences`.
Con eso, una invocación real de `madrono-tfm-dev-cams_calidad_aire` ya NO falla
con 403 "licences not accepted" — la autenticación y la licencia están
confirmadas funcionando.

Pero al procesar el fichero NetCDF real devuelto por la API (distinto del
fixture/mock usado durante el desarrollo original), la función falla ahora con
un error distinto:

```
ValueError: Incorrectly formatted CF date-time unit_string
  File "ingesta/capturas/cams_calidad_aire_madrid.py", line 448, in lambda_handler
    records = fetch_forecast(config)
  File "ingesta/capturas/cams_calidad_aire_madrid.py", line 402, in fetch_forecast
    return normalize_forecast_zip(zip_bytes, captured_at, model=config.model)
  File "ingesta/capturas/cams_calidad_aire_madrid.py", line 389, in normalize_forecast_zip
    records.extend(normalize_forecast_file(archive.read(name), captured_at, model=model))
  File "ingesta/capturas/cams_calidad_aire_madrid.py", line 332, in normalize_forecast_file
    valid_datetimes = netCDF4.num2date(...)
```

`normalize_forecast_file` (línea ~332 y ~340 de
`ingesta/capturas/cams_calidad_aire_madrid.py`) llama a
`netCDF4.num2date(time_var[:], time_var.units, ...)` asumiendo que
`time_var.units` es una cadena de unidades CF estándar (p.ej.
`"hours since 1900-01-01 00:00:00.0"`). El fixture usado para desarrollar y
testear esta función aparentemente tenía ese formato; el fichero NetCDF real
que devuelve la API de CAMS no, y `cftime` no puede parsearlo.

## Objetivo

Diagnosticar el formato real de `time_var.units` (y `frt_var.units` si aplica)
que devuelve la API de CAMS en producción, y corregir `normalize_forecast_file`
para que lo parsee correctamente, sin asumir un único formato si la API puede
variar.

## Alcance concreto

1. Invoca `madrono-tfm-dev-cams_calidad_aire` (región `eu-west-1`) o, mejor,
   reproduce la llamada real a la API de CAMS localmente (usando
   `CAMS_ADS_API_KEY`, disponible en SSM en
   `/madrono-tfm/dev/secrets/cams-ads-api-key` si esta EC2 tiene permisos para
   leerlo, o pidiéndola de nuevo si no) para obtener un NetCDF real y poder
   inspeccionar `dataset.variables["time"].units` (y `.calendar` si existe)
   directamente con un script de diagnóstico rápido.
2. Corrige `normalize_forecast_file` en
   `ingesta/capturas/cams_calidad_aire_madrid.py` para manejar el formato real
   (puede ser tan simple como pasar el `calendar` correcto a `num2date`, o
   requerir normalizar la cadena de unidades antes de pasarla). Prioriza una
   solución robusta frente a una que solo funcione para el caso concreto
   observado, pero sin sobre-ingenierizar: si la API es consistente, no hace
   falta manejar N formatos hipotéticos.
3. Actualiza/crea tests con un fixture NetCDF real (o una réplica fiel de su
   estructura de unidades) que cubra este caso — el fixture anterior no lo
   detectó porque no reflejaba el formato real.
4. Regenera la muestra commiteada en `ingesta/capturas/samples/` para
   `cams_calidad_aire_madrid.py` con datos reales (ya no debería quedar
   `is_mock: true` si las credenciales y la licencia están disponibles en este
   entorno).
5. Si el fix requiere cambios de código, reconstruye el `.zip` de la Lambda
   (mismo mecanismo que la tarea 031/039) y aplica el cambio con
   `terraform apply -target=aws_lambda_function.producer["cams_calidad_aire"]`
   (alcance acotado, no toques las otras 13 funciones).
6. Invoca la función real tras el fix y confirma que completa sin error y
   escribe registros reales en Bronze.

## Restricciones

- Alcance: solo `cams_calidad_aire_madrid.py` (código, tests, muestra) y, si
  hace falta reempaquetar/redesplegar, solo esa Lambda concreta — NO toques
  las otras 13 funciones ni ningún fichero `.tf` no relacionado con esta.
- NO ejecutes `terraform destroy`.
- Si tras el fix aparece un problema distinto y no trivial (por ejemplo, algo
  relacionado con el mapeo `no_conc`/`dust_conc` sin contrastar que ya
  documenta el módulo), no intentes resolverlo aquí — documenta el hallazgo en
  `doc/045-arreglo-parseo-fecha-cams.md` y déjalo para una tarea de
  seguimiento.

## Criterios de aceptación

- `normalize_forecast_file` parsea correctamente las fechas del NetCDF real
  devuelto por la API de CAMS.
- Una invocación real de `madrono-tfm-dev-cams_calidad_aire` completa sin error
  y escribe un objeto real (no mock) en Bronze.
- Test(s) que reproducen el bug original y confirman el arreglo.
- `doc/045-arreglo-parseo-fecha-cams.md` documenta el diagnóstico (formato real
  de `time_var.units` encontrado) y el arreglo.
