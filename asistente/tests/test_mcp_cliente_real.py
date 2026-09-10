"""FIL_73 — un cliente MCP **por HTTP real** contra la app montada.

Ni los streams en memoria (`test_mcp_transport.py`) ni el subproceso stdio
pasan por la protección DNS-rebinding del SDK (`allowed_hosts`), que es lo
que provocó el `421 Misdirected Request` en la EC2 pública y se encontró a
mano. Aquí se levanta la app en un puerto efímero y:

  - un `ClientSession` real sobre `streamable_http` lista las tools;
  - un POST crudo con `Host: 35-42-164-183.nip.io` NO recibe 421 — falla si
    alguien revierte el `allowed_hosts` de `asistente/main.py`.

Arranca un servidor, así que se salta con un mensaje claro si el entorno no
puede enlazar un socket / no tiene `uvicorn`.
"""

from __future__ import annotations

import socket
import threading
import time
import unittest

try:
    import httpx
    import uvicorn

    _DEPS = True
except Exception:  # noqa: BLE001
    _DEPS = False

from asistente.mcp_agent.server import NOMBRES_TOOLS

_ESPERADAS = set(NOMBRES_TOOLS)


def _puerto_libre() -> bool:
    try:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.close()
        return True
    except OSError:
        return False


class _Servidor:
    """Levanta `create_app()` con uvicorn en un hilo, puerto efímero."""

    def __enter__(self):
        from asistente.main import create_app

        cfg = uvicorn.Config(create_app(), host="127.0.0.1", port=0, log_level="error")
        self._srv = uvicorn.Server(cfg)
        self._t = threading.Thread(target=self._srv.run, daemon=True)
        self._t.start()
        for _ in range(200):
            if self._srv.started:
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("uvicorn no arrancó a tiempo")
        self.port = self._srv.servers[0].sockets[0].getsockname()[1]
        self.base = f"http://127.0.0.1:{self.port}"
        return self

    def __exit__(self, *exc):
        self._srv.should_exit = True
        self._t.join(timeout=5)


@unittest.skipUnless(_DEPS and _puerto_libre(), "necesita uvicorn/httpx y poder enlazar un socket")
class ClienteMcpRealTests(unittest.TestCase):
    def test_list_tools_por_http_coincide_con_el_registro(self):
        import anyio
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async def escenario(url):
            async with streamable_http_client(url) as streams:
                read, write = streams[0], streams[1]
                async with ClientSession(read, write) as s:
                    await s.initialize()
                    return await s.list_tools()

        with _Servidor() as srv:
            res = anyio.run(escenario, f"{srv.base}/mcp-server/mcp")
        self.assertEqual({t.name for t in res.tools}, _ESPERADAS)

    def test_host_publico_no_recibe_421(self):
        # `35-42-164-183.nip.io` está en `allowed_hosts` (asistente/main.py).
        # Sin ese ajuste, el SDK MCP responde 421 a cualquier Host != 127.0.0.1.
        with _Servidor() as srv:
            r = httpx.post(
                f"{srv.base}/mcp-server/mcp",
                headers={
                    "Host": "35-42-164-183.nip.io",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
                json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                timeout=10,
            )
        self.assertNotEqual(r.status_code, 421, r.text)


if __name__ == "__main__":
    unittest.main()
