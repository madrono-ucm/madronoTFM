"""Transformación Bronze -> Silver -> Gold del dataset `cartelera_cines_estrenos`
(tarea 055, noveno dataset del patrón).

Mismo patrón que `procesamiento/silver_gold/trafico/` (tarea 041) y el resto
de datasets ya replicados (ver `procesamiento/README.md`). Diferencia
relevante: esta fuente no es una serie temporal de medidas -- es un catálogo
de sesiones/proyecciones de cine (película, cine, horario), así que este
dataset tampoco tiene ningún `geo.py` (no hay ninguna coordenada que
reproyectar: la ubicación de un cine no forma parte del esquema de este
dataset) y su agregación de Gold no sigue el patrón `(id, fecha, hora)` de
medida-numérica del resto -- ver el docstring de `aggregate.py`.

Solo `transform.py` y `aggregate.py` son importables sin dependencias de
terceros (Python puro). `ge_suite.py` y los `glue_*.py` requieren
`pyspark`/`great_expectations` (el entorno de ejecución real de un Glue Job)
y no se importan desde aquí a propósito, para no romper la importación del
paquete en entornos que no los tengan instalados (como esta EC2 de
desarrollo).
"""
