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

    def test_toda_tool_del_chat_es_ejecutable(self):
        # regresión FIL_70: `consulta_grafo` estaba en `_TOOLS_CHAT` (se
        # ofrecía al modelo) pero `_ejecutar_tool` la rechazaba por no estar
        # en `_DESCRIPCIONES` -> "herramienta desconocida" en bucle. Ahora
        # ambos salen del mismo registro (`server.NOMBRES_CHAT`), así que no
        # pueden discrepar; este test lo fija.
        import asistente.mcp_agent.tools as tm
        from asistente.mcp_agent.server import DESCRIPCIONES_CHAT, NOMBRES_CHAT

        for nombre in NOMBRES_CHAT:
            self.assertTrue(callable(getattr(tm, nombre, None)), f"{nombre} no es ejecutable")
            self.assertIn(nombre, DESCRIPCIONES_CHAT, f"{nombre} sin descripción para el LLM")
            # no lo rechaza la puerta de _ejecutar_tool (fallaría antes de llamar a la tool)
            self.assertNotEqual(
                chat._ejecutar_tool(nombre, {}).get("motivo", ""),
                f"herramienta no disponible en el chat: {nombre!r}",
            )

    def test_ejecutar_tool_devuelve_siempre_el_mismo_contrato(self):
        # FIL_71 (mitad segura): {disponible, motivo, datos}, nunca una forma
        # de error ad-hoc.
        import asistente.mcp_agent.tools as tm

        with patch.object(tm, "consulta_grafo", lambda **kw: {"ok": True}):
            r = chat._ejecutar_tool("consulta_grafo", {"plantilla": "x", "lugar": "y"})
        self.assertEqual(r, {"disponible": True, "motivo": None, "datos": {"ok": True}})

        # tool fuera del subconjunto del chat -> no disponible, sin excepción
        r2 = chat._ejecutar_tool("tool_que_no_existe", {})
        self.assertEqual(set(r2), {"disponible", "motivo", "datos"})
        self.assertFalse(r2["disponible"])
        self.assertIsNone(r2["datos"])

        # una tool que revienta -> disponible=false + motivo, no propaga
        with patch.object(tm, "consulta_grafo", lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))):
            r3 = chat._ejecutar_tool("consulta_grafo", {})
        self.assertFalse(r3["disponible"])
        self.assertIn("boom", r3["motivo"])

        # un centinela de "sin datos" del payload se traduce a disponible=false
        with patch.object(tm, "calidad_aire", lambda **kw: {"indice_calidad": "sin_datos"}):
            r4 = chat._ejecutar_tool("calidad_aire", {"zona": "x"})
        self.assertFalse(r4["disponible"])
        self.assertIn("sin datos", r4["motivo"])

    def test_sin_think_quita_bloques_de_razonamiento(self):
        self.assertEqual(chat._sin_think("<think>uhm</think>Hola"), "Hola")
        self.assertEqual(chat._sin_think("<THINK>a\nb</THINK>  R"), "R")
        self.assertEqual(chat._sin_think("sin think"), "sin think")
        self.assertIsNone(chat._sin_think(None))


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

    def test_extra_kw_desactiva_el_razonamiento_solo_para_qwen(self):
        with patch("asistente.chat._MODEL", "llama-3.3-70b-versatile"):
            self.assertEqual(chat._extra_kw(), {})
        with patch("asistente.chat._MODEL", "qwen/qwen3.8-27b"):
            self.assertEqual(chat._extra_kw(), {"reasoning_effort": "none"})


class ObservabilidadTests(unittest.TestCase):
    """FIL_73: logging estructurado de tool-calls + latencia del LLM +
    contadores en `metricas()`."""

    def setUp(self):
        for k in chat._METRICAS:
            chat._METRICAS[k] = 0

    def test_ejecutar_tool_emite_una_linea_con_duracion_y_ok(self):
        import asistente.mcp_agent.tools as tm

        with patch.object(tm, "calidad_aire", lambda **kw: {"indice_calidad": "buena", "estaciones": ["A", "B"]}):
            with self.assertLogs("asistente.chat", level="INFO") as cm:
                r = chat._ejecutar_tool("calidad_aire", {"zona": "Retiro"})
        self.assertTrue(r["disponible"])
        lineas = [m for m in cm.output if "tool=calidad_aire" in m]
        self.assertEqual(len(lineas), 1, cm.output)
        self.assertRegex(lineas[0], r"tool=calidad_aire dur_ms=\d+ ok=True filas=2")
        self.assertEqual(chat._METRICAS["tool_calls"], 1)
        self.assertEqual(chat._METRICAS["tool_calls_ko"], 0)

    def test_ejecutar_tool_cuenta_los_fallos(self):
        import asistente.mcp_agent.tools as tm

        with patch.object(tm, "consulta_grafo", lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))):
            with self.assertLogs("asistente.chat", level="INFO"):
                chat._ejecutar_tool("consulta_grafo", {})
        chat._ejecutar_tool("no_existe_como_tool", {})
        self.assertEqual(chat._METRICAS["tool_calls"], 2)
        self.assertEqual(chat._METRICAS["tool_calls_ko"], 2)

    def test_completar_registra_latencia_y_cuenta_429(self):
        c = CompletarReintentoTests._FakeClient([_Err(429), "ok"])
        with patch("asistente.chat.time.sleep"), self.assertLogs("asistente.chat", level="INFO") as cm:
            chat._completar(c, model="x", messages=[])
        self.assertTrue(any("llm_dur_ms=" in m and "reintentos=1" in m for m in cm.output), cm.output)
        self.assertEqual(chat._METRICAS["llm_429"], 1)
        self.assertEqual(chat._METRICAS["llm_llamadas"], 1)

    def test_health_expone_los_contadores(self):
        from asistente.main import create_app
        from fastapi.testclient import TestClient

        chat._METRICAS["llm_429"] = 3
        with TestClient(create_app()) as cli:
            body = cli.get("/health").json()
        self.assertEqual(body["chat"]["llm_429"], 3)
        self.assertIn("tool_calls", body["chat"])


class FrescuraDatosTests(unittest.TestCase):
    """FIL_73: un resultado vacío distingue 'sin cobertura' de 'sin datos
    recientes (pipeline pausado)'."""

    def test_centinela_sin_datos_da_un_motivo_explicativo(self):
        import asistente.mcp_agent.tools as tm

        with patch.object(tm, "calidad_aire", lambda **kw: {"indice_calidad": "sin_datos"}):
            r = chat._ejecutar_tool("calidad_aire", {"zona": "Vicálvaro"})
        self.assertFalse(r["disponible"])
        self.assertRegex(r["motivo"], r"pausada desde 2026-08-30")
        self.assertIn("zona", r["motivo"])  # menciona la otra causa posible


# --- FIL_95: traza de herramientas del turno + catálogo ---------------------

class _Msg:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _ToolCall:
    def __init__(self, name, arguments="{}", id="tc-1"):
        self.id = id
        self.function = type("Fn", (), {"name": name, "arguments": arguments})()


class _Resp:
    def __init__(self, msg):
        self.choices = [type("Choice", (), {"message": msg})()]


class _ScriptedClient:
    """`chat.completions.create` devuelve, en orden, cada `_Msg` envuelto."""

    def __init__(self, mensajes):
        self._it = iter(mensajes)
        self.chat = self
        self.completions = self

    def create(self, **kw):
        return _Resp(next(self._it))


class PasosDelTurnoTests(unittest.TestCase):
    """`chat()` devuelve `pasos` con las tools de ESTE turno (FIL_95)."""

    def _run(self, mensajes, **tool_stubs):
        import asistente.mcp_agent.tools as tm
        from contextlib import ExitStack

        with ExitStack() as st:
            st.enter_context(patch.object(chat, "_cliente", lambda: _ScriptedClient(mensajes)))
            for nombre, fn in tool_stubs.items():
                st.enter_context(patch.object(tm, nombre, fn))
            return chat.chat("da igual", [])

    def test_dos_tools_dan_dos_pasos_con_ok_ms_y_filas(self):
        out = self._run(
            [
                _Msg(tool_calls=[_ToolCall("calidad_aire", '{"zona":"Retiro"}', "a"),
                                 _ToolCall("trafico_cercano", '{"lugar":"Atocha"}', "b")]),
                _Msg(content="El aire está bien y el tráfico es fluido."),
            ],
            calidad_aire=lambda **kw: {"indice_calidad": "buena", "estaciones": ["E1", "E2"]},
            trafico_cercano=lambda **kw: {"nivel_trafico": "fluido"},
        )
        self.assertEqual([p["tool"] for p in out["pasos"]], ["calidad_aire", "trafico_cercano"])
        self.assertTrue(all(p["ok"] for p in out["pasos"]))
        self.assertTrue(all(isinstance(p["ms"], int) for p in out["pasos"]))
        self.assertEqual(out["pasos"][0]["filas"], 2)  # 2 estaciones

    def test_respuesta_sin_tools_da_pasos_vacio(self):
        out = self._run([_Msg(content="¡Hola! ¿En qué te ayudo?")])
        self.assertEqual(out["pasos"], [])
        self.assertIn("respuesta", out)

    def test_una_tool_que_falla_queda_como_ok_false(self):
        def _boom(**kw):
            raise RuntimeError("Neo4j caído")

        out = self._run(
            [
                _Msg(tool_calls=[_ToolCall("consulta_grafo", "{}", "x")]),
                _Msg(content="No he podido consultar el grafo."),
            ],
            consulta_grafo=_boom,
        )
        self.assertEqual(len(out["pasos"]), 1)
        self.assertFalse(out["pasos"][0]["ok"])


class CatalogoEndpointTests(unittest.TestCase):
    """`GET /chat/catalogo` — una entrada con ejemplo por tool del chat, del
    registro único (FIL_95). Guarda de que ninguna tool del chat se queda
    sin ejemplo."""

    def test_una_entrada_por_tool_del_chat_todas_con_ejemplo(self):
        from fastapi.testclient import TestClient

        from asistente.main import create_app
        from asistente.mcp_agent.server import NOMBRES_CHAT

        r = TestClient(create_app()).get("/chat/catalogo")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(
            {e["tool"] for e in data}, set(NOMBRES_CHAT),
            "toda tool con en_chat=True necesita un ejemplo_chat en el registro",
        )
        for e in data:
            self.assertTrue(e["ejemplo"].strip(), f"{e['tool']} sin ejemplo")
            self.assertTrue(e["titulo"].strip())
            self.assertTrue(e["descripcion"].strip())


if __name__ == "__main__":
    unittest.main()
