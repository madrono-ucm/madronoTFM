"""Tests del esqueleto de la app FastAPI: que arranca y que /health responde."""

import unittest

from fastapi.testclient import TestClient

from asistente.main import create_app


class HealthEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_health_returns_ok_status(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["servicio"], "madrono-asistente")

    def test_health_reports_current_environment(self):
        response = self.client.get("/health")
        self.assertIn("entorno", response.json())


class AppFactoryTests(unittest.TestCase):
    def test_create_app_builds_a_valid_openapi_schema(self):
        app = create_app()
        schema = app.openapi()
        self.assertEqual(schema["info"]["title"], "Madroño - asistente conversacional")

    def test_create_app_returns_independent_instances(self):
        self.assertIsNot(create_app(), create_app())


class McpTransportHostHeaderTests(unittest.TestCase):
    """Regresión: `mcp.streamable_http_app()` sin argumentos activa por
    defecto protección DNS-rebinding restringida a `Host: 127.0.0.1` (SDK
    `mcp`, ver `create_app()`), así que cualquier `Host` real de producción
    (`35-42-164-183.nip.io`) recibía `421 Misdirected Request` -- bug real
    descubierto probando un cliente MCP de verdad contra la instancia
    pública, nunca detectado por los tests existentes (`test_mcp_transport.py`
    usa streams en memoria, sin pasar por este middleware)."""

    def _post(self, host: str):
        # El `StreamableHTTPSessionManager` arranca su task group en el
        # `lifespan` combinado de `create_app()` -- hace falta entrar el
        # `TestClient` como context manager (no basta instanciarlo) para que
        # se ejecute antes de la petición.
        with TestClient(create_app()) as client:
            return client.post(
                "/mcp-server/mcp",
                headers={"Host": host, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            )

    def test_host_publico_real_no_recibe_421(self):
        self.assertNotEqual(self._post("35-42-164-183.nip.io").status_code, 421)

    def test_host_no_reconocido_sigue_bloqueado(self):
        self.assertEqual(self._post("evil-dns-rebinding.example.com").status_code, 421)


if __name__ == "__main__":
    unittest.main()
