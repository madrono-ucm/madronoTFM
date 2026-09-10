"""FIL_93 — el número y la tabla de tools de los README salen de una sola
fuente (`asistente.mcp_agent.server.TOOLS`) y se generan; nada de conteos a
mano que se desincronizan.
"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from asistente import gen_tabla_tools
from asistente.mcp_agent.server import NOMBRES_TOOLS, TOOLS


class GenTablaToolsTests(unittest.TestCase):
    def test_readmes_al_dia(self):
        # Si esto falla: corre `python -m asistente.gen_tabla_tools` y commitea.
        buf = io.StringIO()
        with redirect_stdout(buf):
            codigo = gen_tabla_tools.main(["--check"])
        self.assertEqual(codigo, 0, buf.getvalue())

    def test_bloque_cita_todas_las_tools_y_el_numero(self):
        bloque = gen_tabla_tools.bloque_tabla()
        self.assertIn(f"**{len(TOOLS)} tools**", bloque)
        for nombre in NOMBRES_TOOLS:
            self.assertIn(f"`{nombre}`", bloque)

    def test_cada_tool_con_endpoint_http_resuelto(self):
        # toda tool tiene su router `asistente/routers/<nombre>.py` con un GET
        for nombre in NOMBRES_TOOLS:
            self.assertRegex(
                gen_tabla_tools._endpoint_http(nombre),
                r"^`GET /[a-z-]+`$",
                f"{nombre}: endpoint HTTP no resuelto",
            )


if __name__ == "__main__":
    unittest.main()
