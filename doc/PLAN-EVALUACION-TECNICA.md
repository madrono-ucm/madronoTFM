# Plan de evaluación técnica completa (29/8, a petición del usuario)

Objetivo: recorrer **todo** el código del proyecto (no solo lo tocado en
incidentes recientes) verificando contra el estado real de AWS/Neo4j/CI —
mismo criterio de QA de toda la sesión, sin excepciones — sin hacer ningún
cambio de código directo. Cada hallazgo que implique un cambio de código se
empaqueta como un ticket `FIL_*` para revisión humana (nunca aplicado
directamente). El propio trabajo de evaluación se trocea en tickets `VIC_*`
(continuando la numeración existente, `VIC_08` en adelante) para dejar
trazabilidad de qué se revisó, cuándo y con qué resultado — no confundir con
los `VIC_01`-`VIC_07` de la Pista Memoria, ya cerrados; estos son de
evaluación técnica, no de redacción de la memoria.

## Alcance, un ticket por módulo

| Ticket | Módulo | Qué se verifica |
|---|---|---|
| `VIC_08` | `ingesta/` | Suite de tests completa; spot-check de captura real contra al menos 2-3 fuentes en vivo; consistencia de los 24 módulos vs lo que documenta `ingesta/README.md` |
| `VIC_09` | `procesamiento/` | Suite de tests completa; frescura real en Athena de los 16 datasets "en producción continua" (no solo los 6 que rompió la tarea 106); puertas Great Expectations |
| `VIC_10` | `grafo/` | Suite de tests completa; estado real de Neo4j (nodos/relaciones) vs lo documentado en `doc/080`/`doc/094`/`doc/107`; enriquecimiento OSM y nodos de aforos (gaps ya conocidos, confirmar que siguen igual o si algo cambió) |
| `VIC_11` | `asistente/` | Suite de tests completa; verificación en vivo de las 7 tools contra Athena/Neo4j/ONNX reales (solo `calidad_aire_prevista` verificada hasta ahora en esta sesión) |
| `VIC_12` | `modelado/` | Suite de tests completa (`ML_01`-`ML_10`); artefactos reales (`modelado/evaluation/artifacts/`) siguen siendo consistentes; estado de los gaps ya conocidos (`ML_01` sin join de meteo/festivos, STGNN sin ONNX) |
| `VIC_13` | `infra/terraform/` | `terraform validate`/`fmt`; drift real tras `FIL_09`/`FIL_10` (debería estar limpio salvo Kafka); revisión de que nada más tiene el mismo anti-patrón de key con hash |
| `VIC_14` | `herramientas/`, CI, cola del demonio, disco | Herramienta de coste; estado real de la CI (`gh run list`); salud del demonio (`journalctl`); disco (tras el resize de la tarea 104) |
| `VIC_15` | Memoria (`documents/Memoria_TFM FV.docx`) | Pasada de consistencia final: ¿algún hallazgo de `VIC_08`-`VIC_14` contradice lo que dice la memoria ya reescrita por `VIC_*`/`VIKT_*`? Si sí, no se edita el `.docx` aquí — se anota como hallazgo para un ticket `VIKT_*` de seguimiento |

## Reglas de ejecución

- **Ningún cambio de código en estos tickets** — son de solo lectura/test.
  Cualquier cosa que deba cambiar en código se convierte en un ticket
  `FIL_*` aparte (con el análisis, la evidencia y, si aplica, un `terraform
  plan`/diff propuesto), nunca aplicado ni comiteado directamente.
- Cada `VIC_*` de este plan se marca `status: done` con una nota "## Hecho"
  al terminar, listando qué se verificó y qué `FIL_*` (si los hay) generó.
- Se ejecutan en el orden de la tabla, pero sin bloquearse entre sí (cada
  módulo es independiente).
