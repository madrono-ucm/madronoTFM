---
kind: vic-eval
title: "Evaluación técnica ronda 5 — secretos en todo el histórico de git con detect-secrets"
owner: Claude (QA)
status: done
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

## Hecho (30/8)

Escaneadas 214 707 líneas añadidas alguna vez en todo `git log --all`
(troceado en 11 partes de 20 000 líneas tras descubrir que
`detect-secrets` da `{}` en silencio, sin error, sobre un fichero único
demasiado grande o fuera de un repo git — aviso metodológico documentado
para quien repita esto). 18 hallazgos `Secret Keyword` (la categoría de
mayor señal), los 18 revisados uno a uno: 2 son la credencial real ya
conocida de `FIL_28`, el resto son placeholders/fixtures explícitamente
ficticios o un valor canario de test que verifica una redacción correcta.
**Cero `FIL_*` nuevos** — confirmado con una herramienta dedicada e
independiente que `FIL_28` sigue siendo el único secreto real jamás
commiteado. Detalle completo, incluido un dato curioso sobre por qué el
`grep` manual de `VIC_19` seguía teniendo valor pese a un escáner de 25+
detectores, en
[`doc/VIC-30-eval-detect-secrets-historico.md`](../doc/VIC-30-eval-detect-secrets-historico.md).

Cierra ronda 5 (`VIC_28`-`30`, 3/3 completados): 1 `FIL_*` nuevo
(`FIL_33`, footgun latente de tipos, severidad baja).
