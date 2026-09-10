"""Genera la tabla de tools MCP de los README desde una única fuente.

Fuente de verdad: `asistente.mcp_agent.server.TOOLS` (la lista con la que se
registran en el servidor MCP) + los routers HTTP de `asistente.routers`.

Sin este generador, el número y la lista de tools vivían copiados a mano en
`asistente/README.md`, el `README.md` raíz, el `description` de
`server.py` y varios tests de conteo -- y se desincronizaban: FIL_29 ya lo
arregló una vez (6->10) y, a fecha de FIL_93, `asistente/README.md` decía
"7 tools" mientras `server.py` decía "19".

El bloque generado va entre los marcadores ``<!-- TOOLS:INI ... -->`` y
``<!-- TOOLS:FIN -->`` de cada README.

Uso::

    python -m asistente.gen_tabla_tools           # reescribe los README
    python -m asistente.gen_tabla_tools --check   # sale con 1 si están desfasados
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path

from asistente.mcp_agent.server import TOOLS

_RAIZ = Path(__file__).resolve().parents[1]
_INI = "<!-- TOOLS:INI (generado por `python -m asistente.gen_tabla_tools`; no editar a mano) -->"
_FIN = "<!-- TOOLS:FIN -->"
_DESTINOS = (_RAIZ / "asistente" / "README.md", _RAIZ / "README.md")


def _endpoint_http(nombre: str) -> str:
    """Ruta HTTP del router `asistente/routers/<nombre>.py` (o «—» si no tiene)."""
    try:
        mod = importlib.import_module(f"asistente.routers.{nombre}")
    except ModuleNotFoundError:
        return "—"
    for ruta in getattr(getattr(mod, "router", None), "routes", []):
        metodos = sorted(m for m in getattr(ruta, "methods", set()) if m not in {"HEAD", "OPTIONS"})
        if metodos:
            return f"`{metodos[0]} {ruta.path}`"
    return "—"


def bloque_tabla() -> str:
    """El Markdown que va entre los marcadores, terminado en salto de línea."""
    filas = "\n".join(
        f"| `{s.fn.__name__}` | {_endpoint_http(s.fn.__name__)} | {s.titulo} |" for s in TOOLS
    )
    return (
        f"**{len(TOOLS)} tools**, todas con lógica real (ninguna con "
        "`NotImplementedError`). Generado desde "
        "`asistente/mcp_agent/server.py::TOOLS`.\n\n"
        "| tool | endpoint HTTP | qué hace |\n"
        "|---|---|---|\n"
        f"{filas}\n"
    )


def _render(path: Path, bloque: str) -> str:
    txt = path.read_text(encoding="utf-8")
    if _INI not in txt or _FIN not in txt:
        raise SystemExit(
            f"{path.relative_to(_RAIZ)} no tiene los marcadores de la tabla de tools; "
            f"añade una línea «{_INI}» y otra «{_FIN}» donde deba ir."
        )
    antes, _, resto = txt.partition(_INI)
    _, _, despues = resto.partition(_FIN)
    return f"{antes}{_INI}\n{bloque}{_FIN}{despues}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="no escribe; sale con 1 si algún README está desfasado",
    )
    args = ap.parse_args(argv)

    bloque = bloque_tabla()
    desfasados = []
    for path in _DESTINOS:
        nuevo = _render(path, bloque)
        if nuevo != path.read_text(encoding="utf-8"):
            desfasados.append(path)
            if not args.check:
                path.write_text(nuevo, encoding="utf-8")

    if args.check:
        if desfasados:
            print("Tabla de tools desfasada en:")
            for p in desfasados:
                print(f"  - {p.relative_to(_RAIZ)}")
            print("Corre:  python -m asistente.gen_tabla_tools")
            return 1
        print(f"tabla de tools al día ({len(TOOLS)} tools)")
        return 0

    for p in _DESTINOS:
        print(f"  actualizado {p.relative_to(_RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
