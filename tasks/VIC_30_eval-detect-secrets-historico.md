---
kind: vic-eval
title: "Evaluación técnica ronda 5 — secretos en todo el histórico de git con detect-secrets"
owner: Claude (QA)
status: pending
created_at: "2026-08-30"
depends_on: []
---

Parte de [`doc/PLAN-EVALUACION-TECNICA-5.md`](../doc/PLAN-EVALUACION-TECNICA-5.md).
Ningún cambio de código — `detect-secrets` instalado solo en el `.venv`
local para esta auditoría.

## Alcance

- `detect-secrets scan` sobre el estado actual del working tree primero
  (barrido rápido de referencia).
- Para cobertura histórica real (el objetivo de este ticket): recorrer
  los commits de todo `git log --all` con `detect-secrets` (o
  reconstruir el árbol en un directorio temporal por commit si hace
  falta) para no depender solo del estado final del repo — el hallazgo de
  `VIC_19`/`FIL_28` (credencial de Bluesky) estaba en un commit antiguo,
  ya corregido en el HEAD actual, así que un escaneo de solo el working
  tree no lo habría encontrado.
- Cada secreto candidato: verificar si ya es conocido (`FIL_28`) o es un
  hallazgo nuevo. Ignorar explícitamente positivos falsos obvios
  (ejemplos de código, fixtures de test con valores claramente ficticios
  como `aaaa-bbbb-cccc-dddd`).
- No autenticarse con ninguna credencial que se encuentre, real o
  aparente — solo reportar.

## Criterios de aceptación

- Cobertura confirmada de todo el histórico (`--all`), no solo el HEAD
  actual.
- Cada hallazgo con veredicto explícito: ya conocido (`FIL_28`), falso
  positivo (con la razón), o nuevo y real (→ ticket `FIL_*`,
  con la misma urgencia que `FIL_28` si aplica — reportar de inmediato,
  no esperar al resumen final).
- Cero cambios de código aplicados aquí.
