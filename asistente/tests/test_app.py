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


if __name__ == "__main__":
    unittest.main()
