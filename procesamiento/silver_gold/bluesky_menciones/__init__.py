"""Transformación Bronze -> Silver -> Gold del dataset `bluesky_menciones`
(tarea 057, undécimo dataset del patrón).

Mismo patrón que `procesamiento/silver_gold/trafico/` (tarea 041) y el resto
de datasets ya replicados (ver `procesamiento/README.md`). Diferencia
relevante: esta fuente son publicaciones de texto libre (contenido, lugar/
distrito buscado, marca de tiempo), no una medida numérica ni un catálogo de
hechos con clave natural fuerte -- la puerta de calidad se centra en
integridad estructural y en descartar contenido vacío o duplicados exactos
dentro del lote (ver docstring de `transform.py`). Tampoco tiene ningún
`geo.py`: Bluesky no publica ninguna coordenada del post.

Solo `transform.py` y `aggregate.py` son importables sin dependencias de
terceros (Python puro). `ge_suite.py` y los `glue_*.py` requieren
`pyspark`/`great_expectations` (el entorno de ejecución real de un Glue Job)
y no se importan desde aquí a propósito, para no romper la importación del
paquete en entornos que no los tengan instalados (como esta EC2 de
desarrollo).
"""
