# 107 — Extender la key estable de `procesamiento_source` (FIL_09/PR #175) a los 48 `glue_script_*`

**Tarea de solo código** (`allow_infra_apply: false`) — sigue el patrón de
dos pasos de `tasks/README.md`: esta tarea prepara el código y el plan; el
`apply` es un paso aparte, revisado y aprobado por un humano, igual que
`FIL_09`.

## Contexto

`doc/FIL-09-terraform-plan-glue-libreria-compartida.md` § "Pendiente"
señalaba, tras resolver el incidente de la librería compartida
(`procesamiento_source`), dos *follow-ups* del mismo anti-patrón (key con
hash de contenido en vez de key estable):

- `aws_s3_object.layer_build_source` (`lambda_layer_build.tf`)
- `aws_s3_object.glue_script_*` (~44/48, `glue.tf`)

## Investigado antes de tocar nada: `layer_build_source` **no tiene el mismo riesgo**

A diferencia de `procesamiento_source` (37 jobs de Glue distintos, cada uno
con su propio `default_arguments["--extra-py-files"]` **congelando** en su
propio estado la key resuelta en el momento de su último `apply` — de ahí
que un `apply -target` parcial pudiera dejar jobs huérfanos apuntando a una
key ya borrada), `layer_build_source` solo tiene **dos usos**, y ambos
derivan la key de la **misma expresión** `local.layer_source_key`
(`lambda_layer_build.tf:40`, recalculada en cada `plan`/`apply`, nunca
"congelada" en el estado de otro recurso):

```
grep -rn "layer_source_key" infra/terraform/*.tf
  lambda_layer_build.tf:40   -> definición del local (incluye el hash)
  lambda_layer_build.tf:146  -> aws_s3_object.layer_build_source.key
  lambda_layer_build.tf:265  -> aws_codebuild_project...source.location
```

Como los dos consumidores calculan la key de la misma forma en cada
operación, un `apply` que solo toque `aws_s3_object.layer_build_source`
(sin incluir el `aws_codebuild_project`) no puede dejar al proyecto de
CodeBuild apuntando a un objeto inexistente — el objeto que sí existe es,
por construcción, el que la fórmula calcula ahora mismo. Además, el propio
código ya documenta el motivo de usar hash aquí a propósito: una política
de expiración (`aws_s3_bucket_lifecycle_configuration.build_artifacts`,
línea ~80) borra sola los `.zip` fuente antiguos que van quedando bajo
distintas keys — un diseño deliberado, no un descuido.

**Conclusión**: no se toca `layer_build_source`. El único follow-up real es
el de los `glue_script_*`.

## `glue_script_*`: mismo riesgo que `procesamiento_source`, menor radio por recurso

Cada uno de los 48 objetos `aws_s3_object.glue_script_*` tiene exactamente
**un** consumidor (`aws_glue_job.<mismo dataset>.command.script_location`,
verificado con `grep` sobre cada uno), que sí congela la key resuelta en su
propio estado. Un `apply -target` que actualizara un script sin incluir su
job (o viceversa) dejaría a **ese job concreto** apuntando a una key
borrada — el mismo patrón que rompió 37 jobs de golpe con
`procesamiento_source`, aquí acotado a 1 job por incidente en vez de 37,
pero el mismo riesgo estructural, repetido 48 veces.

## Qué se hizo

En `infra/terraform/glue.tf`, para los 48 recursos
`aws_s3_object.glue_script_*`:

1. **Key estable**: `glue-scripts/<nombre>-${filemd5(...)}.py` →
   `glue-scripts/<nombre>.py`. El `etag` (ya presente en todos) sigue
   disparando la reescritura in situ del mismo objeto cuando el script
   cambia — sin key nueva, sin objeto huérfano posible.
2. **`lifecycle { create_before_destroy = true }`** en los 48 (uno de los
   48, `glue_script_afluencia_lugares_silver_to_gold`, tenía un formato de
   bloque ligeramente distinto — comentario propio de `FIL_06` y
   `bucket = ` con un espacio en vez de dos — y no lo capturó la
   transformación automática del resto; añadido a mano). Cubre la
   migración one-shot desde la key con hash: el objeto nuevo se crea antes
   de borrar el antiguo, así el job correspondiente nunca ve un hueco
   mientras dura el `apply`.

No se tocó ningún `aws_glue_job`, `aws_lambda_function` ni ningún otro
recurso — sus referencias a `.key` ya apuntan automáticamente a la key
estable en cuanto se recalculan en el próximo `plan`/`apply` (es un
atributo computado, no algo que haya que editar a mano en 48 sitios más).

## Verificación

```
$ terraform fmt -check -recursive
(sin salida, ya formateado)
$ terraform validate
Success! The configuration is valid.
```

Plan (solo lectura, mismo método de `-target` de `FIL_09` para excluir
Kafka — nunca aplicado, ver tareas 042/098):

```
Plan: 48 to add, 67 to change, 48 to destroy.
```

- **48 to add / 48 to destroy**: los 48 `aws_s3_object.glue_script_*`
  migrando de la key con hash a la key estable (`must be replaced`,
  `create_before_destroy` en efecto — verificado que cada uno muestra el
  símbolo `+/-`, no un `-/+` que implicaría destruir antes de crear).
- **67 to change**: los `aws_glue_job.*` correspondientes actualizando su
  `script_location` a la key estable (in-place, sin *replace*), las 14
  `aws_lambda_function.producer[*]` (drift preexistente no relacionado con
  esta tarea — el paquete compartido de Lambda cambió por trabajo de otras
  sesiones, no por este cambio), `aws_codebuild_project` y
  `aws_iam_policy.scheduler_invoke_lambda` (dependientes indirectos).
- **Verificado con `grep` que no hay ninguna destrucción suelta**: los 48
  `destroy` son exactamente la mitad-baja de los 48 pares `must be
  replaced` de los scripts.
- `aws_s3_object.procesamiento_source` aparece como **`updated in-place`**
  (no *replace*) — confirma que la key estable de `FIL_09`/PR #175 sigue
  funcionando como se diseñó.

## Pendiente (no de esta tarea)

- **El `apply` de este cambio** — código listo, sin aplicar. Necesita el
  mismo criterio de aprobación humana que `FIL_09`/tareas 098/100. No es
  urgente (a diferencia de `FIL_09`, hoy no hay ningún job roto), es una
  mejora preventiva.
- `layer_build_source` se queda como está, a propósito (ver análisis
  arriba) — no crear un ticket para "arreglarlo", no es un bug.
