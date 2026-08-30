---
kind: vic-eval
title: "Evaluación técnica ronda 5 — seguridad de IaC con checkov sobre Terraform"
owner: Claude (QA)
status: pending
created_at: "2026-08-30"
depends_on: []
---

Parte de [`doc/PLAN-EVALUACION-TECNICA-5.md`](../doc/PLAN-EVALUACION-TECNICA-5.md).
Ningún cambio de código — `checkov` instalado solo en el `.venv` local
para esta auditoría.

## Alcance

- `checkov -d infra/terraform/` (solo lectura, no toca ningún recurso
  real ni corre `terraform plan`/`apply`).
- Cada hallazgo `FAILED` de severidad media/alta: leer el `.tf` real antes
  de decidir si es un falso positivo (p. ej. una regla pensada para un
  entorno de producción crítico puede no aplicar a un proyecto de TFM de
  coste 0 con datos públicos no sensibles) o un problema real que valga
  la pena corregir.
- Prestar atención especial a IAM (políticas demasiado permisivas) y a
  cualquier recurso de almacenamiento (S3/similar) sin cifrado o con
  acceso público — son las categorías con mayor impacto real si son
  ciertas.

## Criterios de aceptación

- Salida completa revisada para severidad media/alta (baja se puede
  resumir).
- Cada hallazgo con veredicto explícito: falso positivo / no aplica al
  contexto del proyecto (con la razón) o real (→ ticket `FIL_*`).
- Cero cambios de código/infraestructura aplicados aquí.
