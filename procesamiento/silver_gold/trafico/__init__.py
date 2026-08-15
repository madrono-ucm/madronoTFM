"""Transformación Bronze -> Silver -> Gold del dataset `trafico` (piloto, tarea 041).

Solo `geo.py`, `transform.py` y `aggregate.py` son importables sin
dependencias de terceros (Python puro, ver `procesamiento/README.md`).
`ge_suite.py` y los `glue_*.py` requieren `pyspark`/`great_expectations`
(el entorno de ejecución real de un Glue Job) y no se importan desde aquí a
propósito, para no romper la importación del paquete en entornos que no los
tengan instalados (como esta EC2 de desarrollo).
"""
