"""Tests del esqueleto de `tools` MCP: firma, docstring y registro.

No hay lógica real que probar todavía (ver `asistente/mcp_agent/tools.py`):
estos tests verifican que el contrato de cada `tool` está bien formado
(tipado completo, docstring) y que las cinco quedan registradas en el
servidor MCP, no su comportamiento.
"""

import asyncio
import inspect
import unittest

from asistente.mcp_agent import tools
from asistente.mcp_agent.server import mcp

TOOL_FUNCTIONS = [
    tools.afluencia_prevista,
    tools.calidad_aire,
    tools.opciones_movilidad,
    tools.disponibilidad_aparcamiento,
    tools.eventos_cercanos,
]


class ToolSignatureTests(unittest.TestCase):
    def test_every_tool_has_a_docstring(self):
        for fn in TOOL_FUNCTIONS:
            with self.subTest(tool=fn.__name__):
                self.assertTrue(fn.__doc__ and fn.__doc__.strip())

    def test_every_tool_parameter_and_return_is_typed(self):
        for fn in TOOL_FUNCTIONS:
            with self.subTest(tool=fn.__name__):
                sig = inspect.signature(fn)
                self.assertIsNot(sig.return_annotation, inspect.Signature.empty)
                for name, param in sig.parameters.items():
                    self.assertIsNot(param.annotation, inspect.Signature.empty, name)

    def test_every_tool_raises_not_implemented(self):
        for fn in TOOL_FUNCTIONS:
            with self.subTest(tool=fn.__name__):
                sig = inspect.signature(fn)
                kwargs = {
                    name: "x"
                    for name, param in sig.parameters.items()
                    if param.default is inspect.Parameter.empty
                }
                with self.assertRaises(NotImplementedError):
                    fn(**kwargs)


class MCPServerRegistrationTests(unittest.TestCase):
    def test_all_tools_are_registered_on_the_mcp_server(self):
        registered = asyncio.run(mcp.list_tools())
        names = {tool.name for tool in registered}
        expected = {fn.__name__ for fn in TOOL_FUNCTIONS}
        self.assertEqual(expected, names)


if __name__ == "__main__":
    unittest.main()
