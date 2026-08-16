"""Transformación Bronze -> Silver -> Gold del dataset `aforos_peatones_bicicletas`
(tarea 054, octavo dataset del patrón).

Mismo patrón que `procesamiento/silver_gold/trafico/` (tarea 041) y el resto
de datasets ya replicados (ver `procesamiento/README.md`). Diferencia
relevante: como en `transporte_publico_emt`/`bicimad`/`aparcamientos`/
`calidad_aire`/`meteorologia`/`ruido`, este dataset no tiene ningún `geo.py`
-- `ingesta/capturas/aforos_peatones_bicicletas_madrid.py`
(`normalize_record`) ya entrega `location.lat`/`location.lon` en WGS84
(coordenadas "agrupadas por puntos" del propio CSV de origen, ya
convertidas), no hace falta ninguna reproyección.

Solo `transform.py` y `aggregate.py` son importables sin dependencias de
terceros (Python puro). `ge_suite.py` y los `glue_*.py` requieren
`pyspark`/`great_expectations` (el entorno de ejecución real de un Glue Job)
y no se importan desde aquí a propósito, para no romper la importación del
paquete en entornos que no los tengan instalados (como esta EC2 de
desarrollo).
"""
