---
id: 104
slug: ec2-root-volume-al-limite
title: 'QA: el volumen raíz de esta EC2 está al 95% (375M libres de 6,7G) — ya causó
  un fallo real de pip install'
status: in_review
force: false
allow_infra_apply: false
branch: task/104-ec2-root-volume-al-limite
pr_number: 171
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/171
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-29T19:20:00+00:00'
updated_at: '2026-08-29T19:03:56.345798+00:00'
started_at: '2026-08-29T18:54:41.682176+00:00'
submitted_at: '2026-08-29T19:03:56.345775+00:00'
merged_at: null
---

## Hallazgo de QA (verificado en vivo)

`df -h /` en esta EC2: **6,7G totales, 6,3G usados, 375M libres (95%)**.
Ya causó un fallo real durante esta sesión (28-29/8): `pip install`
de las dependencias de `modelado/` (pandas/pyarrow/lightgbm/shap/
matplotlib) falló con `OSError: [Errno 122] Disk quota exceeded` hasta
que se liberó espacio borrando el caché de pip (~968M). El stack de ML
que ahora vive en este EC2 (`torch`, `lightgbm`, `mlflow`, `onnx`,
`onnxruntime`, `pandas`, etc., **934M** solo en
`~/.local/lib/python3.14/site-packages`) es sustancialmente más pesado
que cuando se aprovisionó la instancia originalmente (tarea 001, pila
Lambda/Glue sin ML).

Con `modelado/` ahora en la CI (tarea 103) y el reentrenamiento nocturno
de `ML_10` corriendo vía `cron` en esta misma instancia, el riesgo no es
puntual: **cualquier operación que necesite espacio temporal
—`pip install`, `terraform init` descargando providers, un `git clone`
grande, o el propio job de reentrenamiento generando artefactos—** puede
fallar por quedarse sin disco, con un margen de solo 375M.

## Objetivo

Dar margen de disco real a esta instancia antes de que un fallo por
disco lleno bloquee el reentrenamiento nocturno de producción o una
sesión interactiva en un momento crítico cerca del cierre (17/9).

## Alcance concreto — dos opciones, no excluyentes

1. **Redimensionar el volumen EBS raíz** (recomendado, coste marginal
   ~0,08 USD/GB-mes): ampliar de 8 GiB actuales a, p. ej., 20-30 GiB.
   Requiere `aws ec2 modify-volume` (o el recurso Terraform si el volumen
   está gestionado como código — verifícalo primero, puede que no lo
   esté, ver la nota de la tarea 014 sobre recursos creados a mano en el
   bootstrap) + `growpart`/`resize2fs` en el sistema de ficheros. **Pide
   aprobación explícita del usuario antes de tocarlo** — es un cambio de
   infraestructura real con coste, aunque pequeño.
2. **Mitigación inmediata sin coste**, mientras se decide lo anterior:
   - Vaciar `~/.cache/pip` de forma rutinaria tras instalar dependencias
     pesadas (ya liberó ~968M una vez esta sesión).
   - `sudo apt-get clean` (paquetes `.deb` descargados).
   - Revisar `/usr/src` (341M, cabeceras de kernel de la actualización
     pendiente detectada en la tarea 100/apt) — si no hace falta
     recompilar módulos de kernel, es un candidato a limpiar.
   - Confirmar que `modelado/mlruns/`, `modelado/mlartifacts/` y
     `modelado/mlflow.db` siguen en `.gitignore` (ya lo están, `ML_04`) y
     no crecen sin límite en disco — considerar una rotación/purga
     periódica si el reentrenamiento nocturno se acumula sin límite.

## Restricciones

- No ejecutes ninguna acción de redimensionado de EBS sin aprobación
  explícita del usuario — es infraestructura real con coste, mismo
  criterio que un `terraform apply`.
- La limpieza de cachés (pip/apt) es segura y no necesita aprobación,
  pero documenta cuánto espacio liberó cada vez.

## Criterios de aceptación

- `df -h /` con un margen razonable (recomendado > 20% libre) tras
  aplicar la mitigación elegida.
- Si se redimensiona el volumen, verificado que el sistema de ficheros
  realmente ve el nuevo tamaño (`df -h` refleja el cambio, no solo
  `aws ec2 describe-volumes`).
- Documentado en `doc/104-...md` qué se hizo y el espacio libre resultante.
