---
kind: vic-eval
title: "Evaluación técnica ronda 2 — auditoría de seguridad dedicada"
owner: Claude (QA)
status: done
created_at: "2026-08-30"
depends_on: []
---

Parte de [`doc/PLAN-EVALUACION-TECNICA-2.md`](../doc/PLAN-EVALUACION-TECNICA-2.md).
Ningún cambio de código en este ticket — auditoría defensiva, sobre un
proyecto propio con acceso ya autorizado.

## Alcance

Ninguna pasada anterior de esta sesión tuvo un enfoque de seguridad
dedicado (de punta a punta, no solo IAM de un recurso concreto):

- **Secretos**: `git log -p` / `git grep` sobre patrones de credenciales
  reales (API keys, tokens, contraseñas) en todo el historial accesible,
  no solo el HEAD actual. Confirmar que `ingesta/capturas/secretos.py`
  (`FIL_17`) es el único camino real hacia credenciales en producción y
  que ningún productor viejo quedó leyendo la variable de entorno en claro
  sin el fallback correcto.
- **IAM de mínimo privilegio**: repasar las políticas nuevas
  (`FIL_16` observabilidad, `FIL_17` secretos) además de las ya existentes
  — ¿algún `Resource: "*"` o acción de más que no se haya notado?
- **Superficie del servidor MCP**: sin auth/rate-limiting (aceptado,
  §7.5) — confirmar que esto está clara y honestamente documentado, no
  solo omitido.
- **Bucket S3**: permisos de acceso público (deberían ser privados) en
  Bronze/Silver/Gold/Athena-results.
- **Gestión de dependencias**: alguna dependencia con vulnerabilidad
  conocida relevante (revisión rápida, no una auditoría CVE exhaustiva).

## Criterios de aceptación

- Ningún secreto real encontrado en el histórico de git (o, si se
  encuentra alguno, reportarlo de inmediato como hallazgo crítico, no
  esperar al resumen final).
- Políticas IAM revisadas con el ARN/acción exactos citados si hay algo
  que ajustar.
- Buckets S3 confirmados privados.
- Cualquier hallazgo → ticket `FIL_*` nuevo, priorizado por severidad.

## Restricciones

- Solo lectura/consulta (`aws iam`, `aws s3api get-bucket-policy`, `git
  log`/`git grep`) — nada de cambios de permisos ni de política.

## Hecho (30/8)

Ver [`doc/VIC-19-eval-seguridad.md`](../doc/VIC-19-eval-seguridad.md).
**Hallazgo crítico real** reportado de inmediato (no al final): posible
credencial real de Bluesky en un fixture de test, en el repo público →
[`FIL_28`](FIL_28_CRITICO-posible-credencial-bluesky-en-repo-publico.md).
Resto de la superficie (buckets S3 privados, IAM sin comodines, MCP sin
auth honestamente documentado) sin hallazgos.
