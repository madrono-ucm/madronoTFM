"""FIL_70 — configuración de proveedor LLM y robustez de `asistente.chat`.

Sin red ni clave real: se prueban el subconjunto de tools del chat, el
reintento de `_completar`, y la lectura de `base_url` / API key del entorno.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from asistente import chat


class _Err(Exception):
    def __init__(self, status_code):
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class SubconjuntoToolsTests(unittest.TestCase):
    def setUp(self):
        chat._tools_schema = None  # invalida la caché entre tests

    def tearDown(self):
        chat._tools_schema = None

    def test_solo_expone_las_tools_del_chat(self):
        esquema = chat._tools_para_groq()
        nombres = {t["function"]["name"] for t in esquema}
        self.assertEqual(nombres, set(chat._TOOLS_CHAT))
        # no cuela ninguna `*_prevista*` / afluencia / opciones_movilidad
        self.assertNotIn("calidad_aire_prevista", nombres)
        self.assertNotIn("afluencia_estimada", nombres)
        for t in esquema:
            self.assertIn("properties", t["function"]["parameters"])


class CompletarReintentoTests(unittest.TestCase):
    class _FakeClient:
        def __init__(self, efectos):
            self._efectos = list(efectos)
            self.llamadas = 0
            self.chat = self  # client.chat.completions.create -> este mismo
            self.completions = self

        def create(self, **kw):
            self.llamadas += 1
            e = self._efectos.pop(0)
            if isinstance(e, Exception):
                raise e
            return e

    def test_reintenta_en_429_y_acaba_bien(self):
        c = self._FakeClient([_Err(429), _Err(503), "ok"])
        with patch("asistente.chat.time.sleep"):
            r = chat._completar(c, model="x", messages=[])
        self.assertEqual(r, "ok")
        self.assertEqual(c.llamadas, 3)

    def test_no_reintenta_en_400(self):
        c = self._FakeClient([_Err(400), "ok"])
        with patch("asistente.chat.time.sleep"), self.assertRaises(_Err):
            chat._completar(c, model="x", messages=[])
        self.assertEqual(c.llamadas, 1)

    def test_propaga_tras_agotar_reintentos(self):
        c = self._FakeClient([_Err(429), _Err(429), _Err(429)])
        with patch("asistente.chat.time.sleep"), self.assertRaises(_Err):
            chat._completar(c, model="x", messages=[])
        self.assertEqual(c.llamadas, chat._MAX_REINTENTOS_LLM)


class ProveedorConfigurableTests(unittest.TestCase):
    def test_api_key_prefiere_llm_api_key(self):
        with patch.dict(os.environ, {"LLM_API_KEY": "abc", "GROQ_API_KEY": "xyz"}):
            self.assertEqual(chat._leer_api_key(), "abc")
        with patch.dict(os.environ, {"GROQ_API_KEY": "xyz"}, clear=False):
            os.environ.pop("LLM_API_KEY", None)
            self.assertEqual(chat._leer_api_key(), "xyz")

    def test_cliente_pasa_base_url(self):
        chat._client = None
        capturado = {}

        def _fake_groq(**kw):
            capturado.update(kw)
            return object()

        with patch("asistente.chat._LLM_BASE_URL", "https://api.cerebras.ai/v1"), \
             patch("asistente.chat._leer_api_key", return_value="k"), \
             patch("asistente.chat.Groq", _fake_groq):
            chat._cliente()
        self.assertEqual(capturado.get("base_url"), "https://api.cerebras.ai/v1")
        chat._client = None


if __name__ == "__main__":
    unittest.main()
