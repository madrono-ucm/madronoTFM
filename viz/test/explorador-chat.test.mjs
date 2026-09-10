// FIL_68 — el panel de chat del explorador del grafo (variante --live):
// se pliega/despliega, las sugerencias rellenan y envían, `/chat` recibe
// mensaje + historial, y un fallo se degrada a un mensaje legible sin
// romper la página.
//
// No arranca maplibre (el stub no dispara "load"), así que `arrancar()` no
// corre: se prueba solo la capa de chat, que se cablea al cargar el script.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM, VirtualConsole } from "jsdom";

const HTML = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "..", "grafo_explorador_live.html"),
  "utf8",
).replace(/\r\n/g, "\n");
const pageScript = HTML.match(/<script>\n([\s\S]*?)<\/script>\s*<\/body>/)[1];

const tick = () => new Promise((r) => setTimeout(r, 0));

function montar(chatHandler) {
  const vc = new VirtualConsole();
  const errores = [];
  vc.on("jsdomError", (e) => errores.push(String(e?.stack || e)));

  const dom = new JSDOM(HTML.replace(/<script[\s\S]*?<\/script>/g, ""), {
    url: "https://asistente.test/grafo/explorador/",
    runScripts: "outside-only",
    virtualConsole: vc,
  });
  const win = dom.window;
  win.addEventListener("error", (e) => errores.push(String(e.error?.stack || e.message)));

  // maplibre: lo mínimo para que el script no lance al construir el mapa.
  // `on` NO dispara "load" -> arrancar() no corre.
  class MapStub {
    addControl() { return this; }
    on() { return this; }
    getSource() { return { setData() {} }; }
    setFilter() {}
    flyTo() {}
    getCanvas() { return { style: {} }; }
  }
  win.maplibregl = { Map: MapStub, NavigationControl: class {} };

  const llamadas = [];
  win.fetch = (u, opts = {}) => {
    const path = String(u).replace(/^https?:\/\/[^/]+/, "");
    llamadas.push({ path, opts });
    if (path.endsWith("/chat")) {
      try {
        const out = chatHandler ? chatHandler() : { status: 200, body: { respuesta: "ok", historial: [1] } };
        if (out instanceof Error) return Promise.reject(out);
        return Promise.resolve({ ok: out.status < 400, status: out.status, json: () => Promise.resolve(out.body || {}) });
      } catch (e) { return Promise.reject(e); }
    }
    return Promise.reject(new Error("sin stub para " + path));
  };

  win.eval(pageScript);
  const $ = (id) => win.document.getElementById(id);
  return { win, $, llamadas, errores };
}

test("FIL_68 · el panel aparece en --live y se pliega/despliega", () => {
  const { win, $ } = montar();
  assert.equal($("chat").hidden, false, "el panel de chat no se mostró en la variante live");
  assert.equal($("chat-body").hidden, true, "debería arrancar plegado");
  assert.equal($("chat-tgl").getAttribute("aria-expanded"), "false");
  $("chat-tgl").dispatchEvent(new win.Event("click"));
  assert.equal($("chat-body").hidden, false, "no se desplegó al pulsar la cabecera");
  assert.equal($("chat-tgl").getAttribute("aria-expanded"), "true");
  $("chat-tgl").dispatchEvent(new win.Event("click"));
  assert.equal($("chat-body").hidden, true, "no se volvió a plegar");
});

test("FIL_68 · una sugerencia despliega, rellena y envía a /chat con historial", async () => {
  const ctx = montar(() => ({ status: 200, body: { respuesta: "La estación Retiro mide O₃.", historial: ["h1"] } }));
  ctx.$("chat-sug").querySelector("button").dispatchEvent(new ctx.win.Event("click"));
  await tick(); await tick();

  const chat = ctx.llamadas.filter((l) => l.path.endsWith("/chat"));
  assert.equal(chat.length, 1, "no se llamó a /chat");
  const enviado = JSON.parse(chat[0].opts.body);
  assert.ok(enviado.mensaje && Array.isArray(enviado.historial));
  const hilo = ctx.$("chat-hilo").textContent;
  assert.match(hilo, /tú:/);
  assert.match(hilo, /asistente:.*Retiro mide O₃/);
  assert.equal(ctx.$("chat-send").disabled, false, "el botón quedó bloqueado");
});

test("FIL_68 · un fallo de /chat se degrada a un mensaje legible, sin romper la página", async () => {
  const ctx = montar(() => ({ status: 502 }));
  ctx.$("chat-body").hidden = false;
  ctx.$("chat-in").value = "¿tráfico en Sol?";
  ctx.$("chat-in").dispatchEvent(Object.assign(new ctx.win.Event("keydown"), { key: "Enter" }));
  await tick(); await tick();

  assert.match(ctx.$("chat-hilo").textContent, /No se pudo consultar el asistente/);
  assert.equal(ctx.$("chat-send").disabled, false);
  assert.deepEqual(ctx.errores, [], "excepción de página en el camino de error");
});

test("FIL_68 · Enter con el input vacío no llama a /chat", async () => {
  const ctx = montar();
  ctx.$("chat-body").hidden = false;
  ctx.$("chat-in").value = "   ";
  ctx.$("chat-in").dispatchEvent(Object.assign(new ctx.win.Event("keydown"), { key: "Enter" }));
  await tick();
  assert.equal(ctx.llamadas.filter((l) => l.path.endsWith("/chat")).length, 0);
});
