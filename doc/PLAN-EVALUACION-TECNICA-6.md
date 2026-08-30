# Plan de evaluación técnica — ronda 6 (cobertura de tests)

**Fecha:** 2026-08-30 · **Contexto:** las rondas 4-5 cubrieron análisis
estático (lint, seguridad, tipos, IaC, dependencias, secretos
históricos) — ninguna mide qué código **no** ejecuta ningún test. Es un
ángulo distinto de los anteriores: no busca patrones sospechosos en el
código, busca huecos de cobertura donde un bug real podría esconderse sin
que ningún test (ni ninguna herramienta estática) lo detecte nunca.
`pytest-cov` no estaba instalado — primera vez que se mide un porcentaje
real de cobertura en este proyecto.

## Ticket

| # | Ticket | Alcance |
|---|---|---|
| `VIC_31` | Medir cobertura de tests con `pytest --cov` | Identificar módulos/funciones de producción con 0% o cobertura muy baja, priorizar por riesgo real (lógica de negocio vs. glue code trivial) |

Sin cambios de código; hallazgos con potencial de bug real → `FIL_*`
nuevo (numeración siguiente: **34**). Un hueco de cobertura no es en sí
mismo un `FIL_*` — solo lo es si, al leer el código sin test, aparece algo
con pinta de bug o de comportamiento no verificado que importe de verdad.
