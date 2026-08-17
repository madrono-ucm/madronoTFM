"""Transformación Bronze -> Silver -> Gold del dataset `aemet_prevision_avisos`
(tarea 058, duodécimo dataset del patrón).

Mismo patrón que `procesamiento/silver_gold/trafico/` (tarea 041) y el resto
de datasets ya replicados (ver `procesamiento/README.md`). Diferencia
relevante: esta fuente combina dos formas de dato de un mismo productor --
previsión diaria por municipio y avisos meteorológicos vigentes -- tratadas
por separado desde `transform.py` hasta `glue.tf` (ver docstring de
`transform.py`).

Solo `transform.py` y `aggregate.py` son importables sin dependencias de
terceros (Python puro). `ge_suite.py` y los `glue_*.py` requieren
`pyspark`/`great_expectations` (el entorno de ejecución real de un Glue Job)
y no se importan desde aquí a propósito, para no romper la importación del
paquete en entornos que no los tengan instalados (como esta EC2 de
desarrollo).
"""
