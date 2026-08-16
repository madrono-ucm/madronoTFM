"""Transformación Bronze -> Silver -> Gold del dataset `transporte_publico_emt` (tarea 046).

Mismo patrón que `procesamiento/silver_gold/trafico/` (tarea 041, ver
`procesamiento/README.md`). Diferencia relevante: este dataset no tiene
ningún `geo.py` -- `ingesta/capturas/transporte_publico_madrid.py` ya entrega
`location.lat`/`location.lon` en WGS84 (coordenadas GeoJSON de la propia API
MobilityLabs), no hace falta ninguna reproyección.

Solo `transform.py` y `aggregate.py` son importables sin dependencias de
terceros (Python puro). `ge_suite.py` y los `glue_*.py` requieren
`pyspark`/`great_expectations` (el entorno de ejecución real de un Glue Job)
y no se importan desde aquí a propósito, para no romper la importación del
paquete en entornos que no los tengan instalados (como esta EC2 de
desarrollo).
"""
