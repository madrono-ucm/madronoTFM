---
kind: vic-eval
title: "Evaluación técnica ronda 4 — CVEs de dependencias con pip-audit"
owner: Claude (QA)
status: done
created_at: "2026-08-30"
depends_on: []
---

Parte de [`doc/PLAN-EVALUACION-TECNICA-4.md`](../doc/PLAN-EVALUACION-TECNICA-4.md).
Ningún cambio de código en este ticket.

## Alcance

- `pip-audit` contra el entorno real (`.venv` de esta EC2, que instala
  `ingesta/requirements.txt` + `modelado/requirements.txt` +
  `asistente/requirements.txt` combinados) — base de datos real de OSV/PyPI.
- Por cada CVE real encontrado: ¿el paquete afectado se usa en una ruta de
  código expuesta a entrada no confiable (una API externa, un input de
  usuario) o solo en un contexto interno/de desarrollo? Prioriza el
  primero.
- No proponer un `pip install -U` genérico sin comprobar que la versión
  nueva no rompe algo (`FIL_23` ya mostró que un cambio de versión de
  `torch` sin cuidado tiene efectos secundarios reales).

## Criterios de aceptación

- Salida completa de `pip-audit` revisada.
- CVEs reales explicados con impacto real en este proyecto, no solo
  copiados de la base de datos.
- Cualquier CVE que amerite acción → ticket `FIL_*` con la versión exacta
  a la que actualizar y qué verificar después.

## Hecho (30/8)

3 CVEs reales, ambos paquetes transitivos (no pineados en ningún
`requirements.txt` propio): `cryptography` 49.0.0 (`CVE-2026-69247`,
oráculo Bleichenbacher en descifrado PKCS7, fix 50.0.0+) y `setuptools`
78.1.0 (`CVE-2025-47273` path traversal CVSS 8.8 + `CVE-2026-59890` bypass
de `MANIFEST.in`, fix 78.1.1+/83.0.0+). Verificado con `grep` que ninguna
de las APIs vulnerables (PKCS7/S-MIME, `PackageIndex.download`,
construcción de sdist) se usa en código propio — impacto real nulo pero
bump recomendado por coste ~0 → **`FIL_32`** con versiones exactas de
destino. `torch` no auditable (build `+cpu` no indexado), limitación de
la herramienta, no un hueco de esta auditoría.

Detalle completo en
[`doc/VIC-27-eval-pip-audit.md`](../doc/VIC-27-eval-pip-audit.md).
Cierra ronda 4 (`VIC_25`-`27`, 3/3 completados).
