"""Transformación Bronze -> Silver -> Gold del dataset `cams_calidad_aire`
(tarea 059, previsión de calidad del aire de Copernicus CAMS para Madrid).

Mismo patrón que `procesamiento/silver_gold/trafico/` (tarea 041) y el resto
de datasets ya replicados (ver `procesamiento/README.md`). Diferencia
relevante: este dataset es una previsión con horizonte (`leadtime_hour`), no
una medida del instante actual -- misma naturaleza de dato que
`aemet_prevision_avisos` (tarea 058), ver docstring de `transform.py`.

Solo `transform.py` y `aggregate.py` son importables sin dependencias de
terceros (Python puro). `ge_suite.py` y los `glue_*.py` requieren
`pyspark`/`great_expectations` (el entorno de ejecución real de un Glue Job)
y no se importan desde aquí a propósito, para no romper la importación del
paquete en entornos que no los tengan instalados (como esta EC2 de
desarrollo).
"""
