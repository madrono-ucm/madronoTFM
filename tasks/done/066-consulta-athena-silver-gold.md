---
id: 66
slug: consulta-athena-silver-gold
title: Capa de consulta SQL sobre Silver/Gold con Amazon Athena
status: done
force: false
allow_infra_apply: true
branch: task/066-consulta-athena-silver-gold
pr_number: 113
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/113
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-20T09:00:00+00:00'
updated_at: '2026-08-20T21:42:17.874048+00:00'
started_at: '2026-08-20T01:37:31.418395+00:00'
submitted_at: '2026-08-20T01:51:09.495688+00:00'
merged_at: '2026-08-20T21:42:14Z'
---

## Contexto

Silver/Gold (tareas 041-065) ya está en producción continua para los 14
datasets: datos reales, limpios, agregados, con tablas ya registradas en el
catálogo de Glue (`aws_glue_catalog_database.silver`/`gold`, creadas/
actualizadas por los propios jobs vía `glue:CreateTable`/`UpdateTable`). Pero
no existe ninguna forma de consultarlos con SQL — son parquet bien
organizado en S3, no un dato "usable". Esta tarea añade Amazon Athena, el
motor de consulta serverless nativo de AWS sobre el catálogo de Glue (pago
solo por dato escaneado, sin ningún clúster que mantener — mismo principio
de coste mínimo que Lambda/Glue en el resto del proyecto).

**`force: false` deliberado**: es la primera vez que se expone una interfaz
de consulta real sobre datos de producción — quiero revisar que las
consultas devuelven lo esperado antes de fusionar.

**Riesgo bajo, alcance sin restricción de `allow_infra_apply`**: a
diferencia de Glue/Lambda, Athena no tiene cómputo persistente ni estado
mutable que puedas romper por accidente — es routing de consultas sobre
datos ya existentes. Aun así, sigue el mismo criterio de aplicar con
`-target` acotado que dejó documentado la tarea 065 (`terraform plan` sin
acotar en este repo también muestra pendiente la infraestructura de Kafka,
tarea 042, deliberadamente sin aplicar — no la toques).

## Objetivo

Desplegar un workgroup de Athena que permita consultar con SQL las tablas
Silver y Gold de los 14 datasets, y verificar con consultas reales contra
datos de producción que el resultado es correcto.

## Alcance concreto

1. Fichero Terraform nuevo (`infra/terraform/athena.tf`): `aws_athena_workgroup`
   (con `enforce_workgroup_configuration = true`, `bytes_scanned_cutoff_per_query`
   razonable como salvaguarda de coste), un bucket S3 nuevo (o un prefijo del
   ya existente `aws_s3_bucket.build_artifacts`, decide y documenta) para los
   resultados de consulta (`output_location`), y una política IAM mínima
   (lectura de Silver/Gold + acceso al catálogo de Glue + escritura del
   bucket de resultados) para el rol/usuario que vaya a consultar — decide
   si conviene un rol IAM dedicado (`madrono-tfm-dev-athena-query-role`) o
   reutilizar uno existente, y documenta por qué.
2. `terraform plan`/`apply` acotado con `-target` a los recursos nuevos de
   este fichero únicamente (sigue el patrón que dejó documentado
   `doc/065-aplicar-scheduling-silver-gold.md` para evitar arrastrar la
   deriva no relacionada de Kafka/`procesamiento/` a este apply).
3. Verifica con al menos 5 consultas SQL reales (`aws athena start-query-execution`
   + `get-query-execution`/`get-query-results`), cubriendo:
   - Una consulta simple sobre una tabla Silver (p.ej. `SELECT COUNT(*) FROM
     silver.trafico`).
   - Una consulta de agregación sobre una tabla Gold (p.ej. intensidad media
     de tráfico por hora del día actual).
   - Una consulta que cruce dos tablas Gold por proximidad temporal (p.ej.
     tráfico y calidad del aire de la misma hora) — no hace falta cruce
     espacial todavía (eso es el grafo Neo4j), solo confirmar que Athena
     puede unir dos datasets con un `JOIN` normal.
   - Una consulta sobre un dataset del grupo "diario" (p.ej. `ruido` o
     `agenda_eventos`).
   - Una consulta sobre alguno de los dos datasets que hoy salen vacíos en
     Silver (`cartelera_cines_estrenos`/`afluencia_lugares`) para confirmar
     que Athena maneja bien una tabla sin particiones con datos, sin error.
4. Documenta en `doc/066-consulta-athena-silver-gold.md` las 5 consultas
   ejecutadas con su resultado real (no inventado), el coste/bytes
   escaneados de cada una, y cualquier problema encontrado (p.ej. si hace
   falta `MSCK REPAIR TABLE`/`add partition` porque el catálogo no descubre
   particiones nuevas automáticamente — Glue sí las registra al escribir,
   pero confírmalo con una consulta real, no lo des por hecho).

## Restricciones

- NO ejecutes `terraform apply` sin `-target` — el repo tiene código sin
  aplicar (Kafka) que no debe desplegarse como efecto colateral.
- NO ejecutes `terraform destroy`.
- NO toques `infra/terraform/lambda.tf` ni `glue.tf` — esta tarea es solo
  sobre Athena, un fichero nuevo.
- No hace falta arreglar la deriva del zip de `procesamiento/` documentada
  en la tarea 065 — no la toques aquí, es una tarea de seguimiento aparte
  si hiciera falta.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/066-...md`, aunque alguna de las 5 consultas no diera el resultado
  esperado — documenta el resultado real, no lo que "debería" salir.

## Criterios de aceptación

- Workgroup de Athena aplicado en AWS real, con salvaguarda de coste
  (`bytes_scanned_cutoff_per_query`).
- Al menos 5 consultas SQL reales ejecutadas contra Silver/Gold de
  producción, con resultado documentado.
- `doc/066-consulta-athena-silver-gold.md` documenta el diseño y los
  resultados reales.
- Hay un commit real con estos cambios.
