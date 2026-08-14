---
id: 25
slug: bronzewriter-soporte-s3
title: 'BronzeWriter: soporte de escritura real en S3'
status: in_progress
force: true
allow_infra_apply: false
branch: task/025-bronzewriter-soporte-s3
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-14T15:41:31+00:00'
updated_at: '2026-08-14T15:43:53.198924+00:00'
started_at: '2026-08-14T15:43:53.198899+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Primer paso para migrar las capturas a producción. La infraestructura del
lakehouse ya está aplicada (tarea 015): el bucket Bronze real es
`madrono-tfm-dev-bronze-222234418587` (`arn:aws:s3:::madrono-tfm-dev-bronze-222234418587`),
con un rol de ingesta (`madrono-tfm-dev-ingestion-role`) que solo puede escribir
ahí. `ingesta/capturas/bronze.py` (`BronzeWriter`, tarea 002) hoy solo escribe en
disco local — este era el plan desde el principio (ver `doc/002-...md`: "el día
que exista el bucket S3... bastará con cambiar esa variable de entorno, sin tocar
código"). Este es ese día.

## Objetivo

Extender `BronzeWriter` para que, cuando `base_path` sea una URI `s3://...`,
escriba de verdad en S3 (vía `boto3`), manteniendo el modo local (disco) sin
cambios para desarrollo/tests — un único cambio compartido por todos los
productores presentes y futuros, sin tocar cada uno de ellos.

## Alcance concreto

1. Añade `boto3` a `ingesta/requirements.txt` (verifica si ya está disponible en
   este entorno vía el rol de instancia EC2 — no debería hacer falta ninguna
   credencial adicional, `boto3` usa las credenciales del rol automáticamente).
2. Modifica `BronzeWriter.__init__`/`write_batch` en `ingesta/capturas/bronze.py`
   para detectar si `base_path` empieza por `s3://` (parsea bucket + prefijo) y, en
   ese caso, escribir el objeto con `s3_client.put_object(...)` en vez de
   `Path.open()` — mismo esquema de partición (`<dataset>/fecha=.../hora=.../<ts>_<sufijo>.json`)
   como key de S3. Si `base_path` es una ruta local (no empieza por `s3://`),
   mantén exactamente el comportamiento actual (no lo toques).
3. `write_batch` debe devolver algo razonable en ambos casos (hoy devuelve un
   `Path`; para S3 puede devolver la key o una URI `s3://bucket/key` — decide un
   tipo de retorno consistente y documenta el cambio si el tipo cambia).
4. Añade tests: con un doble de `boto3` (sin red real, sin credenciales reales)
   que verifique que, dado un `base_path` `s3://...`, se llama a `put_object` con
   el bucket/key esperados; y que el modo local sigue funcionando exactamente
   igual que antes (no debe romper ningún test existente de las tareas 002-024 que
   dependan de `BronzeWriter`).
5. Actualiza el docstring de `bronze.py` y la sección relevante de
   `ingesta/README.md` para documentar el nuevo modo S3 y cómo activarlo
   (`BRONZE_BASE_PATH=s3://madrono-tfm-dev-bronze-222234418587/`).

## Restricciones

- NO cambies el comportamiento del modo local existente.
- NO escribas de verdad en el bucket S3 real durante esta tarea (los tests deben
  usar un doble/mock de `boto3`, no `boto3` real contra AWS) — el objetivo de esta
  tarea es el código, no una escritura real todavía.
- No toques ningún productor individual (`trafico_madrid.py` y demás) salvo que
  sea estrictamente necesario para que sigan pasando sus tests tras el cambio.

## Criterios de aceptación

- `BronzeWriter` escribe en S3 vía `boto3` cuando `base_path` es `s3://...`, y en
  disco local exactamente como antes en cualquier otro caso.
- Todos los tests existentes del proyecto (incluidos los de las tareas 002-024)
  siguen pasando.
- `ingesta/README.md` documenta el nuevo modo S3.
