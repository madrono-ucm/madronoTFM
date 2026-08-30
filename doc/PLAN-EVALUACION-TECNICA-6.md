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

## Cierre (30/8) — 1/1 completado

`VIC_31`: 74 % de cobertura total. El 26 % restante es sistemáticamente
orquestación (Glue/CLI/Neo4j-loader) ya verificada en vivo por diseño, no
un hueco de riesgo oculto — los dos casos que merecían lectura completa
(`cargar_grafo.py`, `shap_explain.py`) se verificaron explícitamente sin
hallazgos. **Cero `FIL_*` nuevos.** Con esta ronda, las 3 rondas de
análisis estático/estructural de esta sesión (4, 5, 6) han cubierto lint,
seguridad de aplicación, CVEs, tipos, seguridad de IaC, secretos
históricos y cobertura de tests — 6 ángulos completamente distintos de
los de las rondas 1-3 (verificación funcional en vivo), con un saldo
total de 3 `FIL_*` nuevos, todos severidad baja y ninguno un bug activo
en producción.
