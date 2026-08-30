"""Verificación del transporte MCP real (`FIL_15`).

No basta con `mcp.list_tools()` en proceso (eso solo mira el registro): aquí
se levanta el servidor `low-level` de `mcp` sobre un par de streams y se
conecta un `ClientSession` de verdad, que hace el handshake `initialize`,
un `list_tools` y un `call_tool` por cada `tool` — el mismo camino que
recorre Claude Desktop, pero sin el pipe del SO (ese lo cubre
`test_stdio_subproceso`, que arranca `python -m asistente.mcp_agent.server`
como subproceso y comprueba el `initialize` + `list_tools`).

Los backends (`run_athena_query`, `run_neo4j_query`) se mockean en el mismo
proceso; el `.onnx` es el real vendido en `asistente/modelos/`.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from functools import partial
from unittest.mock import patch

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.memory import create_client_server_memory_streams

from asistente.mcp_agent import tools
from asistente.mcp_agent.server import mcp

_ESPERADAS = {
    "afluencia_estimada", "afluencia_prevista", "calidad_aire",
    "calidad_aire_prevista", "trafico_cercano", "trafico_prevista",
    "opciones_movilidad", "disponibilidad_aparcamiento", "eventos_cercanos",
}


def _aire_mock(instante: datetime, n=25):
    base = instante.replace(minute=0, second=0, microsecond=0)
    return [
        {
            "station_id": "28079008", "station_name": "Ramón y Cajal",
            "pollutant": "NO2", "unit": "µg/m³",
            "date": (base - timedelta(hours=k)).date().isoformat(),
            "hour": (base - timedelta(hours=k)).hour,
            "avg_value": 40.0 + k * 0.5, "lat": 40.45, "lon": -3.68,
        }
        for k in range(n)
    ]


def _trafico_grafo():
    return [{"estacion_id": "trafico:PM10001", "distancia_m": 90.0}]


def _trafico_gold(instante: datetime, n=25):
    base = instante.replace(minute=0, second=0, microsecond=0)
    return [
        {
            "point_id": "PM10001",
            "date": (base - timedelta(hours=k)).date().isoformat(),
            "hour": (base - timedelta(hours=k)).hour,
            "avg_service_level": 2.0 + (k % 3) * 0.3, "lat": 40.42, "lon": -3.70,
        }
        for k in range(n)
    ]


async def _run_client(escenario):
    """Levanta el servidor low-level sobre streams en memoria y ejecuta
    `escenario(session)` contra un `ClientSession` conectado."""
    ll = mcp._lowlevel_server
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        c_read, c_write = client_streams
        s_read, s_write = server_streams
        async with anyio.create_task_group() as tg:
            tg.start_soon(
                partial(
                    ll.run, s_read, s_write,
                    ll.create_initialization_options(), raise_exceptions=True,
                )
            )
            async with ClientSession(c_read, c_write) as session:
                await session.initialize()
                resultado = await escenario(session)
            tg.cancel_scope.cancel()
        return resultado


class TransporteEnMemoriaTests(unittest.TestCase):
    def test_list_tools_expone_las_9(self):
        async def escenario(session):
            return await session.list_tools()

        res = anyio.run(_run_client, escenario)
        self.assertEqual({t.name for t in res.tools}, _ESPERADAS)
        for t in res.tools:
            with self.subTest(tool=t.name):
                self.assertTrue((t.description or "").strip(), "sin descripción para el cliente")
                self.assertIn("properties", t.input_schema)
                # FIL_24: las 9 tools deben anunciar output_schema (antes,
                # opciones_movilidad y eventos_cercanos no, por devolver
                # list[BaseModel] a secas).
                self.assertIsNotNone(t.output_schema, f"{t.name} sin output_schema")
                self.assertIn("properties", t.output_schema)

    def test_call_tool_prevista_devuelve_estructura(self):
        ahora = datetime(2026, 8, 17, 10)

        async def escenario(session):
            return await session.call_tool(
                "calidad_aire_prevista",
                {"zona": "cajal", "horizonte_horas": 6, "momento": ahora.isoformat()},
            )

        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=_aire_mock(ahora)):
            res = anyio.run(_run_client, escenario)
        self.assertFalse(res.is_error, getattr(res, "content", None))
        datos = res.structured_content
        self.assertIsNotNone(datos)
        self.assertTrue(datos["disponible"])
        self.assertIsNotNone(datos["valor_previsto"])
        self.assertEqual(datos["horizonte_horas"], 6)
        self.assertIn("calidad_aire_h6.onnx", datos["modelo"])
        self.assertIsNotNone(datos["momento_objetivo"])

    def test_call_tool_trafico_prevista_por_el_transporte(self):
        ahora = datetime(2026, 8, 17, 10)

        async def escenario(session):
            return await session.call_tool(
                "trafico_prevista",
                {"lugar": "retiro", "horizonte_horas": 3, "momento": ahora.isoformat()},
            )

        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=_trafico_grafo()), \
             patch("asistente.mcp_agent.tools.run_athena_query", return_value=_trafico_gold(ahora)):
            res = anyio.run(_run_client, escenario)
        self.assertFalse(res.is_error, getattr(res, "content", None))
        self.assertTrue(res.structured_content["disponible"])
        self.assertEqual(res.structured_content["punto_id"], "PM10001")

    def test_call_tool_degradado_no_es_error_de_protocolo(self):
        """Un backend caído se traduce en objeto con `motivo`, no en
        `isError` ni excepción de transporte."""
        async def escenario(session):
            return await session.call_tool(
                "calidad_aire_prevista", {"zona": "cajal", "horizonte_horas": 6},
            )

        def _boom(*a, **k):
            raise RuntimeError("Athena no responde")

        with patch("asistente.mcp_agent.tools.run_athena_query", side_effect=_boom):
            res = anyio.run(_run_client, escenario)
        self.assertFalse(res.is_error)
        self.assertFalse(res.structured_content["disponible"])
        self.assertIsNone(res.structured_content["valor_previsto"])
        self.assertIn("Athena", res.structured_content["motivo"])


class TransporteStdioSubprocesoTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_subproceso_hace_handshake_y_lista_tools(self):
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "asistente.mcp_agent.server"],
        )
        with anyio.fail_after(60):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    info = await session.initialize()
                    self.assertEqual(info.server_info.name, "madrono")
                    tools_result = await session.list_tools()
        self.assertEqual({t.name for t in tools_result.tools}, _ESPERADAS)


if __name__ == "__main__":
    unittest.main()
