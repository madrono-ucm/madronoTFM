"""FIL_46 — `mejor_hora_zona`: acceso en lenguaje natural a la **capa social**
del mapa animado (`FIL_45`).

Resuelve una zona de Madrid escrita en texto libre («Vallecas», «distrito
centro», «13») a uno de los 21 distritos y hace el barrido **«mejor hora
hoy»** para un perfil de sensibilidad: para cada hora del día curado calcula
la exposición media de la zona (tráfico previsto + NO₂ + O₃ + ruido diario),
ponderada con los mismos pesos que `ruta_saludable` (`FIL_37`), y devuelve la
franja más limpia.

Compone sustrato que ya existe — no entrena ni consulta nada nuevo:
reutiliza `asistente.ruta_saludable` (que lee `asistente/modelos/
grafo_ruta.json`, vendorizado por `viz/build_grafo_ruta.py`). Python puro,
sin `networkx` ni Neo4j.

Es **petición-respuesta, sin estado**: las *alertas anticipadas por
distrito* que también describe `FIL_46` (avisar cuando la previsión cruza un
umbral OMS/UE) siguen siendo trabajo futuro — faltan un canal de
notificación y una política de umbral por distrito.

Encuadre (`FIL_45`): agregados por zona, sin datos personales; describe el
aire y la hora previstos, no señala barrios; apoyo a la decisión, no consejo
médico. Sirve los 3 días curados de agosto 2026 como demostración de
metodología (§7.4).
"""

from __future__ import annotations

import math
import unicodedata

from asistente import ruta_saludable as _ruta

_SENALES = _ruta._SENALES  # ("traf", "no2", "o3", "noise")
_HORAS = tuple(range(24))

# Coloquialismos -> fragmento(s) del nombre canónico del distrito. Solo hacen
# falta donde el nombre oficial no es obvio o una palabra cubre dos distritos.
_ALIASES: "dict[str, tuple[str, ...]]" = {
    "vallecas": ("puente de vallecas", "villa de vallecas"),
    "san blas": ("san blas - canillejas",),
    "canillejas": ("san blas - canillejas",),
    "moncloa": ("moncloa - aravaca",),
    "aravaca": ("moncloa - aravaca",),
    "el pardo": ("fuencarral - el pardo",),
    "pardo": ("fuencarral - el pardo",),
    "fuencarral": ("fuencarral - el pardo",),
    "pilar": ("fuencarral - el pardo",),
    "prosperidad": ("chamartín",),
    "cuatro caminos": ("tetuán",),
    "casco historico": ("centro",),
    "casco antiguo": ("centro",),
    "chamberi": ("chamberí",),
    "tetuan": ("tetuán",),
    "chamartin": ("chamartín",),
    "vicalvaro": ("vicálvaro",),
    "tetuán": ("tetuán",),
}


def disponible() -> bool:
    return _ruta.disponible()


def _normaliza(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    t = t.lower()
    for basura in ("distrito de ", "distrito ", "barrio de ", "barrio ", "zona de ", "zona "):
        if t.strip().startswith(basura):
            t = t.strip()[len(basura):]
    return " ".join(t.split())


def _mapa_distritos(g) -> "dict[str, str]":
    """`{id_distrito: nombre}` a partir de los nodos del grafo (cada nodo
    trae `distrito` + `distrito_nombre`)."""
    clave = "_mejor_hora_zona_distritos"
    if clave not in g:
        g[clave] = {
            n["distrito"]: n.get("distrito_nombre") or n["distrito"]
            for n in g["nodos"]
        }
    return g[clave]


def zonas_disponibles() -> "list[str]":
    g = _ruta._cargar(_ruta._ARTEFACTO)
    return sorted(_mapa_distritos(g).values())


def _resolver_zona(g, zona: str) -> "tuple[str, str]":
    """Texto libre -> `(id_distrito, nombre)`. `ValueError` si no resuelve o
    es ambiguo, con la lista de distritos en el mensaje."""
    mapa = _mapa_distritos(g)
    por_nombre_norm = {_normaliza(v): k for k, v in mapa.items()}
    q = _normaliza(zona)
    if not q:
        raise ValueError(f"zona vacía; distritos: {', '.join(sorted(mapa.values()))}")

    # 1) id de distrito literal ("13", "01", 1)
    cand = q.zfill(2) if q.isdigit() else q
    if cand in mapa:
        return cand, mapa[cand]

    # 2) nombre exacto normalizado
    if q in por_nombre_norm:
        k = por_nombre_norm[q]
        return k, mapa[k]

    # 3) alias coloquial
    if q in _ALIASES:
        frags = _ALIASES[q]
        hits = [
            (k, v) for k, v in mapa.items()
            if any(f in _normaliza(v) for f in frags)
        ]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise ValueError(
                f"«{zona}» abarca varios distritos ({', '.join(v for _, v in hits)}); "
                "indica cuál"
            )

    # 4) subcadena del nombre del distrito (en ambos sentidos)
    hits = [
        (k, v) for k, v in mapa.items()
        if q in _normaliza(v) or _normaliza(v) in q
    ]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise ValueError(
            f"«{zona}» es ambiguo ({', '.join(v for _, v in hits)}); indica el distrito exacto"
        )

    raise ValueError(
        f"no reconozco la zona «{zona}»; distritos de Madrid: {', '.join(sorted(mapa.values()))}"
    )


def _nodos_de_distrito(g, dist_id: str) -> "list[str]":
    clave = f"_mejor_hora_zona_nodos_{dist_id}"
    if clave not in g:
        g[clave] = [n["id"] for n in g["nodos"] if n["distrito"] == dist_id]
    return g[clave]


def _exposicion_zona_hora(g, dia: str, hora: int, node_ids: "list[str]", pesos: dict) -> float:
    """Media sobre los nodos del distrito de `Σ_señal pesos·norm(exposición)`
    — la misma agregación por nodo que usa `ruta_saludable`, promediada en
    vez de sumada por arista."""
    total, n = 0.0, 0
    for nid in node_ids:
        ex = _ruta._expo_nodo(g, dia, hora, nid)
        acc, w_usado = 0.0, 0.0
        for s in _SENALES:
            v = ex[s]
            if v is None:
                continue
            acc += pesos[s] * _ruta._norm(g, s, v)
            w_usado += pesos[s]
        if w_usado <= 0:
            continue
        total += acc
        n += 1
    return total / n if n else 0.0


def _mejor_franja(serie: "list[float]") -> "tuple[int, int]":
    """Racha más larga de horas consecutivas con exposición ≤ mínimo + 20 %
    del rango. Devuelve `(hora_inicio, hora_fin)` inclusive."""
    lo, hi = min(serie), max(serie)
    umbral = lo + 0.20 * (hi - lo) if hi > lo else lo
    mejor_ini, mejor_len = serie.index(lo), 1
    ini, longitud = None, 0
    for h, v in enumerate(serie):
        if v <= umbral + 1e-12:
            ini = h if ini is None else ini
            longitud += 1
            if longitud > mejor_len:
                mejor_ini, mejor_len = ini, longitud
        else:
            ini, longitud = None, 0
    return mejor_ini, mejor_ini + mejor_len - 1


def mejor_hora_zona(zona: str, perfil: str = "general", *, dia: str | None = None) -> dict:
    """Barrido «mejor hora hoy» para una zona (distrito) y un perfil.

    `dia` None -> el último día curado. Devuelve un dict con la franja más
    limpia, la mejor y la peor hora, la reducción de exposición entre ambas y
    la serie horaria completa (24 valores). `ValueError` si la zona no
    resuelve, el perfil no es válido o el día está fuera de rango.
    """
    g = _ruta._cargar(_ruta._ARTEFACTO)
    if perfil not in g["perfiles"]:
        raise ValueError(f"perfil {perfil!r} no válido; usa {list(g['perfiles'])}")
    dia = dia or g["dias"][-1]
    if dia not in g["exposicion"]:
        raise ValueError(f"día {dia!r} fuera de rango; días: {g['dias']}")

    dist_id, nombre = _resolver_zona(g, zona)
    node_ids = _nodos_de_distrito(g, dist_id)
    pesos = g["perfiles"][perfil]

    serie = [
        round(_exposicion_zona_hora(g, dia, h, node_ids, pesos), 4)
        for h in _HORAS
    ]
    h_mejor = min(_HORAS, key=lambda h: serie[h])
    h_peor = max(_HORAS, key=lambda h: serie[h])
    f_ini, f_fin = _mejor_franja(serie)
    reduccion = (
        (serie[h_peor] - serie[h_mejor]) / serie[h_peor] * 100
        if serie[h_peor] > 0 else 0.0
    )
    return {
        "zona_consultada": zona,
        "perfil": perfil,
        "distrito": nombre,
        "distrito_id": dist_id,
        "dia": dia,
        "n_nodos_zona": len(node_ids),
        "mejor_hora": h_mejor,
        "peor_hora": h_peor,
        "franja_inicio": f_ini,
        "franja_fin": f_fin,
        "reduccion_vs_peor_pct": round(reduccion, 1),
        "serie_horaria": serie,
    }


def dias() -> "list[str]":
    return _ruta.dias()


def perfiles() -> "list[str]":
    return list(_ruta._cargar(_ruta._ARTEFACTO)["perfiles"])
