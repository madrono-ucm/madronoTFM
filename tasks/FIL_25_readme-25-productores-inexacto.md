---
kind: fil
title: "README raíz dice '25 productores... Lambda + EventBridge Scheduler' -- solo 16 lo son de verdad, 8 son carga batch puntual o un módulo retirado"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-30"
resolved_at: "2026-08-30"
---

## Resolución (2026-08-30)

`README.md` raíz corregido:

- Diagrama Mermaid: la caja "Ingesta" pasa a tener **dos nodos** — "16
  productores en continuo (Lambda + EventBridge Scheduler)" y "7 cargas
  batch de referencia (ejecución puntual → grafo / muestra)". Solo el primero
  entra en la cadena Bronze→Silver→Gold; el segundo va directo a Neo4j.
- Fila de layout de `ingesta/`: "16 productores en continuo
  (`lambda.tf::local.producers`) + 7 cargas batch de referencia + 1 módulo
  retirado (`afluencia_lugares_madrid`, `FIL_06`)".

16 verificado contra `infra/terraform/lambda.tf::local.producers`. La cifra
"25" no aparecía en ningún otro README.

> **Contexto**: encontrado verificando `FIL_19` (README raíz) en la ronda de
> QA de `doc/PLAN-REVISION-TFM.md` — contraste directo contra
> `infra/terraform/lambda.tf` (`local.producers`, la fuente de verdad de qué
> está desplegado) y `aws s3 ls` sobre el bucket Bronze real.

## Qué está impreciso (verificado en vivo)

`README.md` (raíz, `FIL_19`) dice en su diagrama de arquitectura:

> "25 productores (`ingesta/capturas/*`) — Lambda + EventBridge Scheduler"

Verificado:

- `ingesta/capturas/*.py` tiene **24 ficheros** reales (excluyendo
  `__init__.py`, `bronze.py` y `secretos.py`, que son helpers, no
  productores).
- `infra/terraform/lambda.tf::local.producers` (la definición real de qué
  Lambda + `EventBridge Scheduler` existe) tiene exactamente **16
  entradas**.
- De los 24 ficheros, **8 no son productores continuos**:
  - `agenda_recintos_madrid.py`, `calendario_laboral_madrid.py`,
    `callejero_madrid.py`, `barrios_distritos_madrid.py`, `poi_madrid.py`,
    `crtm_red_transporte_madrid.py`, `enriquecimiento_osm_lugares.py` — los
    7 llevan **en su propio docstring** "Carga batch puntual... (muestra,
    referencia)" — verificado además que **ninguno tiene prefijo en Bronze
    real** (`aws s3 ls s3://madrono-tfm-dev-bronze-.../` no devuelve
    `recinto`/`callejero`/`calendario`).
  - `afluencia_lugares_madrid.py` — "**RETIRADO (FIL_06)**... Este módulo ya
    no se despliega."
- 24 ficheros − 8 batch/retirados = 16, que **coincide exactamente** con
  `local.producers`. La cifra "25" no reconcilia con ninguna de las dos
  cuentas reales (24 ficheros, 16 productores Lambda).

## Por qué importa

- El README raíz es lo primero que lee un revisor/tribunal — el diagrama de
  arquitectura etiqueta los "25 productores" bajo un único rótulo
  "Lambda + EventBridge Scheduler", dando a entender que los 25 están
  automatizados en continuo. Solo 16 lo están; 7 son cargas puntuales de
  referencia (alimentan el grafo directamente o dan una muestra commiteada,
  ver `grafo/extract.py`) y 1 está retirado por completo.
- No es un error grave (la información correcta está en `lambda.tf` y en
  los propios docstrings), pero sobreestima el grado de automatización real
  justo en el documento más visible del repo.

## Qué investigar / hacer (sin aplicar nada aquí)

1. Corregir el README raíz: separar "16 productores en producción continua
   (Lambda + EventBridge Scheduler)" de "7 cargas batch puntuales de
   referencia (ejecución manual/una vez, alimentan el grafo o dan una
   muestra commiteada)" + "1 módulo retirado (`afluencia_lugares_madrid`,
   `FIL_06`)".
2. Revisar si el propio diagrama Mermaid necesita un matiz visual (p. ej.
   una caja aparte para "referencia / batch puntual" en vez de fusionarla
   con "Ingesta — ruta fría por lotes").
3. Contrastar si el mismo "25" aparece en algún otro sitio nuevo (`asistente/README.md`,
   `modelado/README.md`) que también necesite el matiz.

## Restricciones

- No se ha editado `README.md` en este ticket — solo verificación
  (`ls ingesta/capturas/`, `local.producers` de `lambda.tf`, `aws s3 ls`
  real sobre Bronze).

## Criterios de aceptación

- README raíz con las cifras exactas (16 continuos / 7 batch / 1 retirado),
  verificable contra `lambda.tf` y `aws s3 ls`.
