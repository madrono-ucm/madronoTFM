"""Transformación Bronze -> Silver -> Gold del dataset `ruido` (tarea 053).

Mismo patrón que `procesamiento/silver_gold/trafico/` (tarea 041),
`procesamiento/silver_gold/transporte_publico_emt/` (tarea 046),
`procesamiento/silver_gold/bicimad/` (tarea 047),
`procesamiento/silver_gold/aparcamientos/` (tarea 048),
`procesamiento/silver_gold/calidad_aire/` (tarea 049) y
`procesamiento/silver_gold/meteorologia/` (tarea 050, ver
`procesamiento/README.md`). Diferencia relevante: la fuente
(`ingesta/capturas/ruido_madrid.py`) es diaria por estación+periodo, no
horaria -- ver `transform.py`/`aggregate.py`. Sin `geo.py`: `normalize_record`
ya entrega `location.lat`/`location.lon` en WGS84 (coordenadas del catálogo
de estaciones acústicas de datos.madrid.es), no hace falta ninguna
reproyección.

Solo `transform.py` y `aggregate.py` son importables sin dependencias de
terceros (Python puro). `ge_suite.py` y los `glue_*.py` requieren
`pyspark`/`great_expectations` (el entorno de ejecución real de un Glue Job)
y no se importan desde aquí a propósito, para no romper la importación del
paquete en entornos que no los tengan instalados (como esta EC2 de
desarrollo).
"""
