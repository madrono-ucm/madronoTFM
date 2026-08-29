---
kind: vic
title: "Memoria §7.4 Limitaciones · §7.5 Futuras líneas"
owner: Víctor
status: done
done_by: "Claude (Sonnet 5)"
done_at: "2026-08-29"
created_at: "2026-08-28"
---

## Fuente técnica

- `NEXT_STEPS.md` §"Estado a 28/8" completo (secciones 2, 3, 4, 5).
- `PLAN.md` bloqueador 3 (decisión editorial sobre alcance recortado).
- `doc/101` (CI no bloquea), `doc/094` (grafo/OSM), `doc/087` (aforos
  descontinuados), `doc/083` (Google Maps).

## §7.4 Limitaciones — lista a escribir (todas verificadas)

- **Ventana de datos corta**: la ingesta en continuo arrancó el 2026-08-14;
  a la entrega hay ~3–4 semanas de histórico horario. Los modelos son una
  demostración de metodología con holdout temporal, no una estimación de
  rendimiento en régimen estacional.
- **Sin ruta caliente / streaming**: el estado "instantáneo" es la última
  agregación horaria de Gold (latencia de hasta ~1 h), no un flujo en vivo.
- **Cobertura heterogénea de fuentes**: EMT llegadas captura 1 parada;
  `aforos_peatones_bicicletas` congelado en 2024-06-30 (histórico, no vivo);
  algunas Gold arrancaron con pocos días.
- **Afluencia de lugares es una señal derivada** (sensores próximos vía
  grafo), no una medición directa de personas; su nivel `bajo/medio/alto`
  es una aproximación documentada.
- **CI no bloquea merges** (`main` sin branch protection; `force: true`
  fusiona sin esperar checks) — riesgo asumido de que un commit con CI roja
  llegue a `main` (`doc/101`).
- **Enriquecimiento OSM del grafo** limitado a una muestra (6 POIs); una
  captura Overpass completa es trabajo futuro.
- **Evaluación del asistente**: no se puede medir la "corrección" de un
  consejo subjetivo; se mide fidelidad a los datos, no acierto.

## §7.5 Futuras líneas — mover aquí (con una frase de por qué se descartó)

- **Kafka + Kafka Connect + registro Avro** y **ruta caliente Flink/KSQL** —
  descartados por coste y operación frente al enfoque serverless a coste 0;
  serían el siguiente paso para latencia sub-minuto y alertas en vivo.
- **Delta Lake** — Parquet + Glue + Athena Partition Projection cubre el
  caso batch a coste 0; Delta aportaría time-travel / MERGE eficiente.
- **Cuadro de mando Power BI** con modelo semántico DAX sobre Gold.
- **Observación por satélite** (Sentinel-5P NO₂) como señal de calidad del
  aire independiente de la red terrestre.
- **Proveedor comercial de afluencia** con licencia (sustituye la señal
  derivada por popularidad medida) para un despliegue productivo.
- **Ocupación de aparcamiento en calle en vivo** (dataset "SER. Tiques de
  aparcamiento").
- Fuentes del radar de `doc/090`: recarga de VE, plazas PMR, infraestructura
  ciclista.
- Nodo físico de bajo coste (Raspberry Pi + sensores) para validar la red
  oficial; app móvil; dimensión de huella de carbono.

## Aceptación

- §7.4 no oculta ninguna de las limitaciones de arriba.
- Cada ítem movido a §7.5 lleva el motivo (coste 0 / alcance / tiempo), no
  se presenta como "no dio tiempo" sin más.

## Hecho (29/8)

§7.4/§7.5 reescritas en `documents/Memoria_TFM FV.docx`. §7.4 pasa de 4 a
7 limitaciones (todas verificadas: ventana de datos corta, sin ruta
caliente, cobertura heterogénea, afluencia como aproximación, CI sin
poder de bloqueo real, OSM limitado a muestra, evaluación del asistente
no mide acierto subjetivo). §7.5 pasa de 5 a 10 futuras líneas, cada una
con el motivo del descarte (coste 0 / alcance / tiempo), incorporando
Kafka/Flink/Delta/Power BI/satélite movidos desde el resto de secciones.
