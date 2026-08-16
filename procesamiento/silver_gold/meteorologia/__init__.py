"""Transformación Bronze -> Silver -> Gold del dataset `meteorologia` (tarea 050).

Mismo patrón que `procesamiento/silver_gold/trafico/` (tarea 041),
`transporte_publico_emt/` (046), `bicimad/` (047), `aparcamientos/` (048) y
`calidad_aire/` (049, ver `procesamiento/README.md`). Igual que esos cuatro
últimos, este dataset no tiene ningún `geo.py` --
`ingesta/capturas/meteorologia_madrid.py` (`normalize_station_record`) ya
entrega `location.lat`/`location.lon` en WGS84 (coordenadas del CSV de
metadatos de estaciones meteorológicas de datos.madrid.es), no hace falta
ninguna reproyección.

Diferencia real frente a `calidad_aire` (ver docstring de `transform.py`):
Bronze de este dataset es "ancho" (una fila por estación+instante con hasta
8 magnitudes como columnas), no "largo" como `calidad_aire` -- `transform.py`
pivota a formato largo (una fila por estación+magnitud+instante) en el
propio paso Bronze->Silver.

Solo `transform.py` y `aggregate.py` son importables sin dependencias de
terceros (Python puro). `ge_suite.py` y los `glue_*.py` requieren
`pyspark`/`great_expectations` (el entorno de ejecución real de un Glue Job)
y no se importan desde aquí a propósito, para no romper la importación del
paquete en entornos que no los tengan instalados (como esta EC2 de
desarrollo).
"""
