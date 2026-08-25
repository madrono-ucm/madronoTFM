---
id: 88
slug: terraform-drift-plan-sin-aplicar
title: 'Infra: plan completo del drift de Terraform (Prioridad 1 de NEXT_STEPS.md) -- sin aplicar nada'
status: pending
force: false
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: null
updated_at: null
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

**Prioridad 1 de `NEXT_STEPS.md`** — más urgente que cualquier feature
nueva, decisión explícita del usuario el 25/8. Lee `NEXT_STEPS.md`
("Prioridad 1") y `doc/083-investigacion-google-maps-arquitectura.md`
("Hallazgo 2" y "Hallazgo 2b") enteros antes de empezar -- son la fuente de
verdad de lo que se descubrió y por qué esta tarea existe.

**Resumen del hallazgo (no lo reinvestigues)**: un `terraform plan` sin
acotar devolvió `53 to add, 61 to change, 65 to destroy`. De eso, **48 son
reemplazos de `aws_s3_object.glue_script_*`** — el código Python empaquetado
de Glue/Lambda desplegado en AWS puede no coincidir con `main` (no se puede
confiar en que las correcciones ya fusionadas estén realmente en ejecución).
**5 son creaciones de infraestructura de Kafka** (tarea 042) -- esperadas,
esa infraestructura se dejó escrita en código deliberadamente sin aplicar,
no es un hallazgo nuevo. El plan sin acotar no llegó a completarse limpio la
primera vez por falta del permiso `codebuild:BatchGetProjects` en el rol
`madrono-terraform-deployer`.

**Advertencia crítica, ya verificada, no la reinvestigues**:
`terraform plan -destroy -target=<un dataset concreto>` arrastró, por
políticas IAM compartidas (`ingestion_lambda_logs`,
`scheduler_invoke_lambda`), la planificación de **destruir los 14
productores Lambda completos y sus 20 schedules de EventBridge** -- probado
solo con `plan`, nunca aplicado. **No uses `-destroy -target` en esta tarea
bajo ninguna circunstancia.**

**Esta tarea es deliberadamente solo la mitad "preparar y mostrar el plan"
del patrón de dos tareas que exige `tasks/README.md` para cambios de
Terraform** ("una tarea que solo prepare y muestre un `terraform plan`, sin
aplicar nada, y otra tarea posterior, creada aparte y solo después de
revisar ese plan, que ya sí aplique"). **`allow_infra_apply: false`
deliberado** -- no apliques nada, ni siquiera el permiso IAM que falta (ver
el punto 1 de Alcance concreto: solo código + `-target` de solo lectura
para ese permiso, no aplicado).

## Objetivo

Producir un `terraform plan` completo y legible del drift real, sin aplicar
ningún cambio en AWS, para que un humano lo revise sección por sección
antes de que exista ninguna tarea que aplique nada.

## Alcance concreto

1. Añade `codebuild:BatchGetProjects` a la política IAM de
   `madrono-terraform-deployer` en el código Terraform (`infra/terraform/`)
   -- **no lo apliques**. Si sin este permiso aplicado de verdad en AWS el
   `terraform plan` sin acotar sigue sin completarse limpio (es el
   resultado esperado, ver Hallazgo 2), documenta exactamente ese error tal
   cual, no lo rodees con ningún otro mecanismo.
2. Si el plan sin acotar no completa por el punto 1, intenta
   `terraform plan -target=<el recurso IAM concreto de esa política>` (modo
   `plan` normal, **nunca** `-destroy`) para al menos mostrar ese cambio
   aislado -- sigue sin aplicar nada.
3. Si consigues un `terraform plan` sin acotar que complete (porque el
   permiso ya estuviera aplicado, o por cualquier otro motivo), vuelca la
   salida completa y literal a
   `doc/088-terraform-drift-plan-sin-aplicar.md`, con una tabla-resumen
   humana que agrupe los cambios por categoría (los 48 `glue_script_*` como
   "redespliegue de código a la versión actual de `main`, sin cambio de
   comportamiento esperado"; los 5 de Kafka como "infraestructura conocida,
   nunca aplicada, tarea 042"; y una lista aparte, destacada, de
   **cualquier cambio que no encaje en esas dos categorías** -- eso es lo
   que un humano necesita revisar con más cuidado).
4. Si el plan sin acotar sigue sin completar por el permiso pendiente,
   documenta igualmente todo lo de arriba con la información disponible
   (el plan acotado del punto 2, el error exacto del plan sin acotar) y dejа
   explícito en `doc/088-...md` que aplicar ese único permiso IAM a mano
   (fuera de este pipeline, por un humano) es el siguiente paso antes de
   que una tarea futura pueda producir el plan completo.
5. No toques ningún fichero `.tf` más allá del punto 1. No ejecutes
   `terraform apply` en ningún caso, ni siquiera acotado a un solo recurso.

## Restricciones

- **No ejecutes `terraform apply` bajo ninguna circunstancia** -- esta
  tarea es solo `plan`.
- **No uses `-destroy -target` en ningún momento** -- ver la advertencia de
  Contexto, es un footgun ya verificado que puede planear destruir toda la
  infraestructura Lambda.
- Si cualquier `terraform plan` (acotado o no) muestra algo que no
  reconozcas como una de las dos categorías esperadas (redespliegue de
  código / infraestructura de Kafka pendiente), **para y documéntalo
  destacado** en vez de asumir que es inofensivo.
- No toques `afluencia_lugares`/Google Maps en esta tarea -- su retirada
  del despliegue en vivo queda empaquetada con la reconciliación general
  (ver `doc/083-...md`, decisión 2), no es el objetivo de esta tarea.

## Criterios de aceptación

- `doc/088-terraform-drift-plan-sin-aplicar.md` documenta el resultado real
  (plan completo si fue posible, o el estado parcial + qué falta si no lo
  fue), con el resumen por categorías y cualquier hallazgo inesperado
  destacado.
- Cero cambios reales aplicados en AWS -- verificable porque
  `allow_infra_apply: false` y no se ha invocado `terraform apply` en
  ningún paso.
- `git status`/`git diff` de `infra/terraform/` al terminar: solo el cambio
  del punto 1 (permiso IAM en código), nada más sin commitear ni revertido
  a medias.
