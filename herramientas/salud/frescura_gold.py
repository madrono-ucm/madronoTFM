"""Chequeo de frescura de la capa Gold (`FIL_16`).

## Por qué

Los incidentes `FIL_09` (37/48 jobs de Glue en `LAUNCH ERROR` durante 28 h) y
`FIL_11` (Gold de ruido/avisos escribiendo 0 filas con el job en
`SUCCEEDED`) se encontraron por QA manual, no por ninguna alarma. Un job de
Glue puede dar `SUCCEEDED` sin datos nuevos indefinidamente. Este script
mira el **dato**, no el estado del job: por cada tabla Gold compara la
partición (o `processed_at`) más reciente con "ahora" y clasifica el desfase
contra un umbral por cadencia.

## Pipeline congelado

La infra está en `pipeline_enabled = false` desde 2026-08-30 (ver
`infra/OPERACION.md`), así que **todo lo horario/diario está estancado a
propósito**. Con `--pipeline-congelado` (o `PIPELINE_ENABLED=false` en el
entorno) el desfase se reporta pero **no** cuenta como fallo: exit 0, salvo
que una tabla marcada como descontinuada aparezca fresca (eso sí sería
anómalo). En producción (sin la flag) cualquier tabla estancada → exit 1:
esa es la señal que habría cazado `FIL_11` el primer día.

## Uso

    python -m herramientas.salud.frescura_gold
    python -m herramientas.salud.frescura_gold --pipeline-congelado
    python -m herramientas.salud.frescura_gold --formato json
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from asistente.athena import GOLD_DATABASE, run_athena_query

HORARIA = "horaria"
DIARIA = "diaria"
DESCONTINUADA = "descontinuada"

# Umbral de desfase (horas) a partir del cual la tabla se considera estancada.
# Generoso respecto a la cadencia nominal: deja margen para el retraso de la
# ingesta + el del job silver→gold (ver doc/041). Granularidad de día: la
# marca es `max(date)` interpretada como las 00:00 UTC de ese día.
UMBRAL_HORAS = {
    HORARIA: 30.0,
    DIARIA: 50.0,
    DESCONTINUADA: None,  # nunca se espera fresca
}

# tabla Gold -> (cadencia, campo de marca temporal, umbral_horas propio | None).
#
# `date` es la partición string 'YYYY-MM-DD' = fecha del DATO. Sólo sirve para
# frescura cuando el dato es del pasado inmediato (medidas horarias). Para
# datasets con partición hacia el FUTURO (eventos de agenda, estrenos de
# cine, avisos AEMET por vigencia, previsión por leadtime) `max(date)` no
# mide frescura -- para esos se usa `processed_at` (columna ISO-8601 = cuándo
# lo escribió el job).
#
# `ruido_por_estacion_periodo_fecha` lleva umbral propio: la fuente municipal
# de ruido publica con varios días de retraso (constatado en `FIL_11`), así
# que su `max(date)` va legítimamente ~1 semana por detrás aunque el pipeline
# esté vivo.
TABLAS = {
    "calidad_aire_por_estacion_contaminante_hora": (HORARIA, "date", None),
    "trafico_por_punto_hora": (HORARIA, "date", None),
    "bicimad_por_estacion_hora": (HORARIA, "date", None),
    "aparcamientos_por_parking_hora": (HORARIA, "date", None),
    "meteorologia_por_estacion_magnitud_hora": (HORARIA, "date", None),
    "transporte_publico_emt_por_parada_hora": (HORARIA, "date", None),
    "bluesky_menciones_por_termino_modo_hora": (HORARIA, "date", None),
    "afluencia_lugares_por_lugar_fecha_hora": (HORARIA, "date", None),
    "ruido_por_estacion_periodo_fecha": (DIARIA, "date", 192.0),
    "agenda_eventos_por_categoria_distrito_fecha": (DIARIA, "processed_at", None),
    "cartelera_cines_estrenos_por_pelicula_cine_fecha": (DIARIA, "processed_at", None),
    "aemet_avisos_por_zona_fecha_nivel": (DIARIA, "processed_at", None),
    "aemet_prevision_por_municipio_leadtime": (DIARIA, "processed_at", None),
    "cams_calidad_aire_por_contaminante_fecha_validez": (DIARIA, "processed_at", None),
    "aforos_peatones_bicicletas_por_estacion_modo_hora": (DESCONTINUADA, "date", None),
}


def _pipeline_congelado_por_defecto() -> bool:
    return os.environ.get("PIPELINE_ENABLED", "").strip().lower() in ("0", "false", "no")


def consulta_marca(tabla: str, campo: str) -> str:
    """SQL para la marca temporal más reciente de `tabla`."""
    col = "date" if campo == "date" else "processed_at"
    return f'SELECT max({col}) AS marca FROM "{tabla}"'


def _parse_marca(marca: "str | None") -> "datetime | None":
    if not marca:
        return None
    texto = str(marca).strip()
    try:
        if len(texto) == 10 and texto[4] == "-":  # 'YYYY-MM-DD'
            return datetime.strptime(texto, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(texto.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _edad_horas(marca_dt: datetime, ahora: datetime) -> float:
    return (ahora - marca_dt).total_seconds() / 3600.0


def evaluar_tabla(
    tabla: str,
    cadencia: str,
    campo: str,
    ahora: datetime,
    *,
    umbral_override: "float | None" = None,
    athena_client=None,
) -> dict:
    """Consulta la marca más reciente de una tabla y la clasifica."""
    filas = run_athena_query(consulta_marca(tabla, campo), GOLD_DATABASE, athena_client=athena_client)
    marca = filas[0].get("marca") if filas else None
    marca_dt = _parse_marca(marca)
    umbral = umbral_override or UMBRAL_HORAS[cadencia]

    if marca_dt is None:
        return {
            "tabla": tabla, "cadencia": cadencia, "marca": marca,
            "edad_horas": None, "umbral_horas": umbral,
            "estado": "sin_datos", "alerta_en_produccion": cadencia != DESCONTINUADA,
        }

    edad = round(_edad_horas(marca_dt, ahora), 1)

    if cadencia == DESCONTINUADA:
        # esperada estancada SIEMPRE; que aparezca fresca es lo anómalo
        estado = "descontinuada_con_datos_nuevos" if edad < UMBRAL_HORAS[DIARIA] else "descontinuada_ok"
        return {
            "tabla": tabla, "cadencia": cadencia, "marca": marca,
            "edad_horas": edad, "umbral_horas": umbral,
            "estado": estado, "alerta_en_produccion": estado == "descontinuada_con_datos_nuevos",
        }

    estancada = edad > umbral
    return {
        "tabla": tabla, "cadencia": cadencia, "marca": marca,
        "edad_horas": edad, "umbral_horas": umbral,
        "estado": "estancada" if estancada else "fresca",
        "alerta_en_produccion": estancada,
    }


def build_report(*, ahora: "datetime | None" = None, athena_client=None) -> dict:
    ahora = ahora or datetime.now(timezone.utc)
    filas = [
        evaluar_tabla(
            tabla, cadencia, campo, ahora,
            umbral_override=umbral_override, athena_client=athena_client,
        )
        for tabla, (cadencia, campo, umbral_override) in TABLAS.items()
    ]
    filas.sort(key=lambda f: (not f["alerta_en_produccion"], f["tabla"]))
    anomalas = [f for f in filas if f["alerta_en_produccion"]]
    return {
        "generado_en": ahora.isoformat(),
        "tablas": filas,
        "n_alertarian_en_produccion": len(anomalas),
    }


def format_table(report: dict) -> str:
    lineas = [
        f"Frescura de Gold @ {report['generado_en']}  "
        f"({report['n_alertarian_en_produccion']} alertarían en producción)",
        f"{'tabla':<52} {'cadencia':<14} {'edad(h)':>9} {'umbral':>7}  estado",
        "-" * 104,
    ]
    for f in report["tablas"]:
        edad = "-" if f["edad_horas"] is None else f"{f['edad_horas']:.1f}"
        umbral = "-" if f["umbral_horas"] is None else f"{f['umbral_horas']:.0f}"
        marca = "  <!>" if f["alerta_en_produccion"] else ""
        lineas.append(f"{f['tabla']:<52} {f['cadencia']:<14} {edad:>9} {umbral:>7}  {f['estado']}{marca}")
    return "\n".join(lineas)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--pipeline-congelado",
        action="store_true",
        default=_pipeline_congelado_por_defecto(),
        help="Trata el estancamiento como esperado (exit 0). Por defecto se "
        "deduce de PIPELINE_ENABLED en el entorno.",
    )
    parser.add_argument("--formato", choices=["tabla", "json"], default="tabla")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    report = build_report()
    report["pipeline_congelado"] = args.pipeline_congelado

    if args.formato == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_table(report))
        if args.pipeline_congelado:
            print(
                "\n[pipeline congelado] el estancamiento horario/diario es esperado; "
                "exit 0. En producción, "
                f"{report['n_alertarian_en_produccion']} tabla(s) habrían disparado alarma."
            )

    if args.pipeline_congelado:
        # sólo es fallo lo verdaderamente anómalo: una fuente descontinuada
        # que de pronto tiene datos nuevos.
        anomalo = any(
            f["estado"] == "descontinuada_con_datos_nuevos" for f in report["tablas"]
        )
        return 1 if anomalo else 0
    return 1 if report["n_alertarian_en_produccion"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
