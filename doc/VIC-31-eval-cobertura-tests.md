# VIC_31 — cobertura de tests con pytest-cov (ronda 6)

**Fecha:** 2026-08-30. `pytest-cov` no estaba instalado — primera vez que
se mide un % de cobertura real en este proyecto.

## Comando

```
pytest ingesta/ procesamiento/ grafo/ asistente/ herramientas/ modelado/ tests/ \
  --cov=ingesta --cov=procesamiento --cov=grafo --cov=asistente --cov=modelado --cov=herramientas \
  --cov-report=term-missing
```

**1005 passed, 1 skipped** (igual que en toda verificación anterior de la
suite esta sesión — no se ha roto nada al instrumentar cobertura).
**Cobertura total: 74 % (19 101 líneas, 4 950 sin cubrir).**

## El 74 % no es el número interesante — de qué está hecho el 26 % restante sí

Filtrado el reporte para excluir `*/tests/*` y ficheros al 100 %, el hueco
se concentra casi entero en 3 categorías, todas coherentes con un patrón
que este proyecto documenta y sigue explícitamente en su propio código
(ver `procesamiento/README.md`, "Por qué Python puro para la lógica, y
PySpark solo en el job de Glue"):

1. **Todos los `glue_*.py` de `procesamiento/silver_gold/*/` al 0 %**
   (~25 ficheros). Son la fina capa PySpark que ejecuta AWS Glue en
   producción — la lógica real vive en `transform.py`/`aggregate.py`
   del mismo directorio, que están sistemáticamente al **93-99 %**
   (verificado mirando varios: `ruido/transform.py` 96 %,
   `trafico/transform.py` 93 %, `transporte_publico_emt/transform.py`
   98 %...). El `glue_*.py` es orquestación PySpark sin PySpark
   instalado en esta EC2 de desarrollo (documentado en el propio
   `README.md` como la razón de tener dos capas) — se verifica en el
   job de Glue real, no con `pytest`. **Esperado, no un hueco real.**
2. **Todos los `ge_suite.py` (Great Expectations) al 0 %**. Son
   definiciones declarativas de las mismas reglas que `validate_record()`
   en `transform.py` (sí cubierto) — configuración, no lógica ejecutable
   propia. **Esperado.**
3. **Scripts `main()`/CLI de `modelado/` al 0 %**: `train_gbt.py`,
   `train_stgnn.py`, `run_all.py`, `run_baselines.py`, y
   `grafo/cargar_grafo.py`. Los 5 son *entry points* (`python -m ...`,
   documentado en su propio docstring) que encadenan llamadas a funciones
   de librería ya testeadas (`modelado/models/gbt.py`,
   `modelado/models/baselines.py`, `grafo/extract.py`/`nodos.py`/
   `cypher.py`, etc.) sin lógica propia significativa.

## Los dos casos que sí merecían lectura antes de descartarlos

- **`grafo/cargar_grafo.py`** (99 líneas, 0 %): leído entero. Es
  literalmente una cadena de llamadas a `extract.*`/`nodos.*`/
  `relaciones.*` (todos testeados por separado) sin ninguna
  transformación ni rama condicional propia — el propio docstring dice
  explícitamente *"No se ejecuta contra ninguna instancia real en esta
  tarea"* (bloqueado por la misma limitación de credenciales de Neo4j
  documentada en `VIC_19`/`doc/VIKT-06-...md`). Un test unitario de este
  fichero sería, en la práctica, un mock de cada llamada verificando que
  se invocan en orden — bajo valor real. **Sin hallazgo.**
- **`modelado/models/shap_explain.py`** (53 líneas, 0 %, sin test
  propio): la única de las 6 con lógica real no trivial (maneja la
  diferencia de forma del retorno de `shap.TreeExplainer` entre
  clasificador binario y regresor, ordena y trunca). Solo se llama desde
  `train_gbt.py` (también 0 %), nunca desde el notebook de demo. Antes de
  descartarlo se verificó que **sí se ha ejecutado de verdad**: existen
  artefactos reales commiteados
  (`modelado/evaluation/artifacts/shap_{calidad_aire,trafico}_h{1,3,6}.png`
  + los `tier1_*_shap.json`), y su contenido es sensato y no degenerado
  (para `calidad_aire` h1: `value` con importancia 13.7, luego
  `value_roll24h_mean` 3.85, orden descendente correcto, magnitudes
  físicamente plausibles — no un `[0, 0, 0, ...]` que delataría un bug
  silencioso). **Verificado en vivo vía artefacto real, sin hallazgo.**

## Ficheros de `ingesta/capturas/*.py` al 54-75 %

El resto del hueco notable son ~20 módulos de `ingesta/capturas/` entre
54 % y 75 %. Muestreadas varias líneas sin cubrir (p. ej.
`trafico_madrid.py:187-193,213-251`, `calidad_aire_madrid.py:269-364`):
son consistentemente el `main()`/parseo de argumentos CLI y el bloque
`if __name__ == "__main__":` de cada script, no las funciones de parseo
(`_parse_*`, `normalize_*`) que sí están cubiertas por los tests unitarios
de cada módulo — mismo patrón que el resto: lógica testeada, wiring de
CLI no. Coherente con que las rondas 1-3 ya verificaron estos módulos en
vivo contra las APIs reales de datos.madrid.es repetidamente.

## Conclusión

**Cero `FIL_*` nuevos.** El 26 % sin cubrir no es un hueco de riesgo
oculto: es, sistemáticamente, orquestación (Glue/CLI/Neo4j-loader) que el
propio proyecto ha decidido verificar en vivo en vez de con `pytest` —
una decisión de arquitectura ya documentada y consistente en todo el
código, no un descuido. Los dos casos que sí merecían una lectura
completa antes de asumir eso (`cargar_grafo.py`, `shap_explain.py`) se
verificaron explícitamente y no escondían ningún bug.
