"""Transformación Bronze -> Silver -> Gold del dataset `afluencia_lugares`
(tarea 060, afluencia estimada de lugares conocidos de Madrid vía la
librería `populartimes`, ver `ingesta/capturas/afluencia_lugares_madrid.py`
y doc/012).

Mismo patrón que `procesamiento/silver_gold/trafico/` (tarea 041) y el resto
de datasets ya replicados (ver `procesamiento/README.md`). Diferencia
relevante: cada registro trae dos magnitudes independientes y de presencia
opcional (`live_pct`, `typical_by_hour`) -- ver docstring de `transform.py`.

Solo `transform.py` y `aggregate.py` son importables sin dependencias de
terceros (Python puro). `ge_suite.py` y los `glue_*.py` requieren
`pyspark`/`great_expectations` (el entorno de ejecución real de un Glue Job)
y no se importan desde aquí a propósito, para no romper la importación del
paquete en entornos que no los tengan instalados (como esta EC2 de
desarrollo).
"""
