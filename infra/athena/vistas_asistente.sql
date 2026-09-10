-- FIL_83 — vistas Athena para las rutas calientes del asistente.
--
-- Varias tools rehacen el mismo "última hora por estación" sobre Gold en
-- cada petición. Estas vistas lo pre-shapean: menos SQL en el código y menos
-- bytes escaneados por consulta. `asistente/athena.py` puede leer la vista si
-- existe y caer a la tabla si no (no es obligatorio para que las tools
-- funcionen).
--
-- Aplicar (cuando se dé el OK — `allow_infra_apply:false` en el ticket):
--   aws athena start-query-execution \
--     --work-group madrono-tfm-dev-silver-gold \
--     --query-execution-context Database=madrono-tfm_dev_gold \
--     --query-string "$(cat infra/athena/vistas_asistente.sql)"
-- (una sentencia por invocación; Athena no ejecuta scripts multi-statement).
--
-- Con el pipeline congelado desde 2026-08-30, "última fecha" es fija; cuando
-- se descongele, las vistas siguen siendo correctas (max(date) dinámico).

-- Última hora con lectura por (estación, contaminante) de calidad del aire.
CREATE OR REPLACE VIEW v_calidad_aire_ultima_hora AS
SELECT t.station_id, t.station_name, t.pollutant, t.pollutant_name, t.unit,
       t.date, t.hour, t.avg_value, t.max_value, t.min_value, t.lat, t.lon
FROM calidad_aire_por_estacion_contaminante_hora t
JOIN (
    SELECT station_id, pollutant, max(date || lpad(cast(hour as varchar), 2, '0')) AS k
    FROM calidad_aire_por_estacion_contaminante_hora
    WHERE avg_value IS NOT NULL
    GROUP BY station_id, pollutant
) m
  ON t.station_id = m.station_id AND t.pollutant = m.pollutant
 AND (t.date || lpad(cast(t.hour as varchar), 2, '0')) = m.k;

-- Última hora con lectura por punto de tráfico.
CREATE OR REPLACE VIEW v_trafico_ultima_hora AS
SELECT t.*
FROM trafico_por_punto_hora t
JOIN (
    SELECT id_punto, max(date || lpad(cast(hour as varchar), 2, '0')) AS k
    FROM trafico_por_punto_hora
    WHERE avg_service_level IS NOT NULL
    GROUP BY id_punto
) m
  ON t.id_punto = m.id_punto
 AND (t.date || lpad(cast(t.hour as varchar), 2, '0')) = m.k;

-- Última lectura por (estación meteo, magnitud).
CREATE OR REPLACE VIEW v_meteo_ultima_hora AS
SELECT t.station_id, t.station_name, t.magnitude, t.date, t.hour,
       t.avg_value, t.max_value, t.min_value, t.lat, t.lon, t.altitude_m
FROM meteorologia_por_estacion_magnitud_hora t
JOIN (
    SELECT station_id, magnitude, max(date || lpad(cast(hour as varchar), 2, '0')) AS k
    FROM meteorologia_por_estacion_magnitud_hora
    WHERE avg_value IS NOT NULL
    GROUP BY station_id, magnitude
) m
  ON t.station_id = m.station_id AND t.magnitude = m.magnitude
 AND (t.date || lpad(cast(t.hour as varchar), 2, '0')) = m.k;
