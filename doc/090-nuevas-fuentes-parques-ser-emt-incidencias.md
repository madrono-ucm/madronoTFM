# 090 — Nuevas fuentes: parques y jardines, calles SER, incidencias EMT

## Qué se investigó y por qué

A petición del usuario, se rastreó el catálogo completo de `datos.madrid.es`
en las categorías `transporte` (109 datasets) y `medio-ambiente` con
frecuencia diaria (10 datasets), cruzado contra los 21 productores ya
existentes en `ingesta/capturas/` (leyendo cada docstring, no solo el
nombre), para encontrar fuentes que llenaran huecos reales del proyecto —
no solo "datos interesantes". El rastreo completo, priorizado, se publicó
como artifact ("Radar de datasets") antes de decidir qué construir.

## Hallazgos que invalidaron dos candidatos de "alta prioridad" del rastreo inicial

Antes de construir nada, se verificó cada candidato contra el dataset real
(formato, frecuencia, campos) — dos de los cuatro candidatos iniciales de
"alta prioridad" resultaron mucho más débiles de lo que sugería su título:

- **"EMT. Grado de ocupación de líneas de autobús"**: se había descrito
  como señal de ocupación de pasajeros en vivo. Verificado contra el
  dataset real: es un **porcentaje de cumplimiento agregado por línea y
  año**, actualizado **anualmente**, no una señal de ocupación en tiempo
  real. Descartado para el uso previsto.
- **"Campañas de aforos de bici, motos y peatonales"**: se había marcado
  como posible sustituto en vivo del ya descontinuado
  `aforos_peatones_bicicletas` (tarea 087). Verificado: es también una
  **campaña anual** (una hora de medición, un mes al año, 15 puntos en 5
  zonas), última actualización 14/5/2024 — mismo perfil de obsolescencia
  que la fuente ya descartada. Descartado.

Los otros dos candidatos de alta prioridad (parques y jardines, SER) sí se
confirmaron viables y se implementaron — ver abajo. "EMT. Incidencias del
servicio" (prioridad alta) también se implementó tras confirmar que es un
feed RSS real y en vivo.

## Qué se implementó

Tres nuevos productores de datos (Fase 1, Ingesta), siguiendo el patrón
establecido de "carga batch puntual, muestra" (sin `BronzeWriter`, sin
`--interval-seconds`, ver `ingesta/README.md`):

- **`ingesta/capturas/parques_jardines_madrid.py`**: parques y jardines
  municipales (dataset `200761-0`), llena el hueco del caso de uso "paseo
  por el parque" (discutido al diseñar `afluencia_estimada`) — hasta ahora
  ningún `:Lugar` de tipo parque existía en el grafo. Captura real: 8
  parques.
- **`ingesta/capturas/ser_calles_madrid.py`**: calles y plazas del
  Servicio de Estacionamiento Regulado (dataset `218228-0`), aparcamiento
  en calle, distinto del ya integrado (rotacional fuera de calle, con Gold
  roto sin diagnosticar desde antes de la tarea 083). Captura real: 10
  tramos.
- **`ingesta/capturas/emt_incidencias_madrid.py`**: incidencias y
  alteraciones del servicio de EMT (dataset `202992-0`, feed RSS en vivo).
  Captura real: 10 incidencias activas.

Las tres capturas se ejecutaron **de verdad** contra las fuentes reales
(no simuladas) desde este entorno de desarrollo local, que sí tiene salida
a Internet aunque no tenga credenciales AWS por defecto (ver hallazgo de
credenciales de la tarea 087, no aplicable aquí — estas fuentes son
públicas, sin autenticación).

## Dos bugs reales encontrados y corregidos durante la implementación (no simulados)

1. **`ser_calles_madrid.py`, `resolve_latest_csv_url`**: el sufijo numérico
   del `id` de cada recurso del dataset SER **no** se corresponde con el
   año de publicación (`218228-26-...` resultó ser el CSV de **2021**,
   mientras que el de 2026 real es `218228-1-...`). Un primer intento de
   este módulo asumía "sufijo más alto = más reciente" y habría descargado
   datos de hace 5 años silenciosamente. Corregido: se resuelve por
   `last_modified`/`created` real vía la API `package_show`, no por el
   `id`.
2. **`ser_calles_madrid.py`, coordenadas `gis_x`/`gis_y` del recurso
   2026**: llegan corruptas en la propia fuente (verificado también en el
   XLSX equivalente, no es un artefacto de parseo CSV) — la coma decimal
   se perdió en algún proceso de conversión de la fuente, dejando un
   entero de 16 dígitos en vez del decimal esperado
   (`"4.427.249.100.000.000"` en vez de `"442724,9100000000"`). Recuperado
   dividiendo por `1e10` — verificado con varios puntos reales que el
   resultado cae dentro del rango plausible de UTM 30N para Madrid.

## Qué queda deliberadamente fuera de esta tarea

Solo la capa de Ingesta (Bronze-only, muestra committeada). **No** se ha
tocado:

- Silver/Gold (Glue, Athena) para estos tres datasets.
- `infra/terraform/` (no se ha creado ningún recurso AWS nuevo).
- El grafo (`grafo/`) ni el asistente (`asistente/`).

Igual que el resto de fuentes del proyecto (tareas 003-024), la captura
Bronze/Silver/Gold/scheduling real de estas tres fuentes es trabajo de
tareas de seguimiento independientes, no de esta sesión.

## Relevante para tareas futuras

- **`parques_jardines_madrid.py`** es el candidato natural para un nuevo
  origen de `:Lugar` en el grafo (`grafo/nodos.py::lugares_from_parques_
  bronze` o similar, mismo patrón que `lugares_from_poi_bronze`).
- **`ser_calles_madrid.py`** podría ser la vía real para desbloquear
  `disponibilidad_aparcamiento` en vez de seguir depurando el Gold roto de
  `aparcamientos` (Prioridad 2 de `NEXT_STEPS.md`) — aunque recuerda que
  esta fuente da capacidad/zonificación estática, no ocupación en tiempo
  real; esa señal necesitaría un dataset adicional ("SER. Tiques de
  aparcamiento").
- **`emt_incidencias_madrid.py`** es una señal directa para
  `opciones_movilidad` (tool pendiente, cruza tráfico + EMT + BiciMAD) —
  evita recomendar una línea con parada suprimida.
- El resto del rastreo (candidatos de prioridad media/baja: infraestructura
  de recarga de VE, plazas para movilidad reducida, infraestructura
  ciclista, mobiliario urbano de parques) queda documentado en el artifact
  "Radar de datasets" para una decisión futura, no descartado.
