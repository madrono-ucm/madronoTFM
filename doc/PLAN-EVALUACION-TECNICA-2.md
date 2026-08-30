# Plan de evaluación técnica — ronda 2 (post FIL_13–FIL_25)

**Fecha:** 2026-08-30 · **Contexto:** la ronda 1 (`VIC_08`–`15`, `doc/PLAN-EVALUACION-TECNICA.md`)
evaluó el estado a 29–30/8. Desde entonces aterrizaron `FIL_13`–`FIL_25`
(9 tools del asistente, hardening MCP, alertado, secretos en runtime,
test e2e, README raíz, export ONNX del STGNN) y `VIKT_06`–`10` (recorrido
e2e, limitaciones consolidadas, auditoría de reproducibilidad, consistencia
final, defensa). La mayor parte ya se verificó en vivo durante el bucle de
vigilancia de esta sesión (cada `FIL_*` se comprobó de forma independiente
al aterrizar, no solo se confió en la descripción del PR) — este plan
**no repite esas comprobaciones**, las referencia y se centra en lo que
todavía no tuvo una pasada de evaluación dedicada con evidencia trazable
en un ticket propio.

## Qué ya está verificado (no se repite aquí)

| Ticket | Verificación ya hecha | Evidencia |
|---|---|---|
| `FIL_13` (trafico_prevista) | Tests, 8→9 tools, inferencia ONNX real contra Athena | mensajes de esta sesión, `doc/VIKT-06-recorrido-e2e.md` |
| `FIL_14` (afluencia_prevista) | Tests, degradación real sin Neo4j | ídem |
| `FIL_15` (hardening MCP, x3 PRs) | Transporte real (`stdio`), envoltorio, degradación, output_schema, instructions/annotations | ídem + `FIL_24` |
| `FIL_16` (alertado) | `frescura_gold.py` ejecutado en vivo, terraform plan limpio | mensajes de esta sesión |
| `FIL_17` (secretos SSM) | 309 tests, terraform plan limpio, IAM acotado | ídem |
| `FIL_18` (test e2e) | Leído completo, no tautológico, 993 tests suite completa | ídem |
| `FIL_19`/`FIL_25` (README raíz) | Cifras verificadas contra `lambda.tf`/`aws s3 ls` | ídem |
| `FIL_20` (STGNN ONNX) | Export real reproducido con grafos de tamaño nunca visto (12/30/50 nodos), paridad ~1e-8 | ídem |
| `FIL_23` (torch CPU) | Instalación fresca verificada 2 veces, tests en verde | ídem |
| `FIL_24` (output_schema) | Verificado en vivo con `ClientSession` real | ídem |
| `VIKT_06`/`07`/`08`/`09` | Ejecutados end-to-end por esta sesión | `doc/VIKT-06/07/08/09-*.md` |

## Qué falta — nuevos tickets `VIC_*` (ronda 2, numeración continúa desde `VIC_15`)

| # | Ticket | Alcance |
|---|---|---|
| `VIC_16` | Asistente — pasada v2 completa | Las 9 tools (no las 7 de `VIC_11`), MCP compliance (transporte, schemas, instructions), calidad de los tests nuevos, revisión de `asistente/models/` |
| `VIC_17` | Modelado — pasada v2 (STGNN ONNX + Tabla 3) | Reproducir el export STGNN desde el registry real (no solo sintético), decidir/recomendar sobre la discrepancia de Tabla 3 con evidencia adicional si aplica |
| `VIC_18` | Terraform — plan completo sin `-target` selectivo por PR | Revisión integral de todo lo nuevo (`observabilidad.tf`, IAM de secretos, `lambda.tf` reestructurado) en un solo plan, no PR a PR |
| `VIC_19` | Seguridad — auditoría dedicada | Secretos no commiteados, IAM de mínimo privilegio en las políticas nuevas, superficie del servidor MCP, permisos del bucket S3 |
| `VIC_20` | Consistencia de documentación | README raíz vs `asistente/README.md` vs `modelado/README.md` vs `infra/OPERACION.md` vs `doc/README.md` — contradicciones, enlaces muertos, términos obsoletos |
| `VIC_21` | CI / daemon / costes — refresco de `VIC_14` | Estado real de GitHub Actions, `madrono-agent`, coste acumulado tras el volumen de PRs de esta ronda |

Cada ticket se ejecuta con datos reales (Athena/S3/Neo4j donde el acceso lo
permita — misma limitación de credenciales de Neo4j vía SSM que el resto
de esta sesión), sin tocar código; cualquier hallazgo de cambio de código
se empaqueta como ticket `FIL_*` nuevo para revisión humana.

## Números libres

- `VIC_*`: próximo **16**.
- `FIL_*`: próximo **26**.
