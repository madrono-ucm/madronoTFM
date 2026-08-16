"""Transformación Bronze -> Silver -> Gold del dataset `calidad_aire` (tarea 049).

Mismo patrón que `procesamiento/silver_gold/trafico/` (tarea 041),
`procesamiento/silver_gold/transporte_publico_emt/` (tarea 046),
`procesamiento/silver_gold/bicimad/` (tarea 047) y
`procesamiento/silver_gold/aparcamientos/` (tarea 048, ver
`procesamiento/README.md`). Diferencia relevante: como en
`transporte_publico_emt`/`bicimad`/`aparcamientos`, este dataset no tiene
ningún `geo.py` -- `ingesta/capturas/calidad_aire_madrid.py`
(`normalize_record`) ya entrega `location.lat`/`location.lon` en WGS84
(coordenadas del CSV de metadatos de estaciones de datos.madrid.es), no hace
falta ninguna reproyección.

Solo `transform.py` y `aggregate.py` son importables sin dependencias de
terceros (Python puro). `ge_suite.py` y los `glue_*.py` requieren
`pyspark`/`great_expectations` (el entorno de ejecución real de un Glue Job)
y no se importan desde aquí a propósito, para no romper la importación del
paquete en entornos que no los tengan instalados (como esta EC2 de
desarrollo).
"""
