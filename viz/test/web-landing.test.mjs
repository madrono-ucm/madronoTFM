// FIL_92 — la landing (`web/index.html`, servida desde S3/CloudFront)
// distingue los estados de red de verdad y nunca deja la UI bloqueada.
//
// Sin red: se carga la página en jsdom con `fetch` simulado y se comprueba
// cada camino (login ok / credenciales / caído / sin red; chat ok / 500 /
// 429 / sin respuesta / sin red) + el botón "Reintentar" + que el endpoint
// se puede fijar con `?api=`.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM, VirtualConsole } from "jsdom";

const HTML = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "..", "..", "web", "index.html"),
  "utf8",
).replace(/\r\n/g, "\n");
const pageScript = HTML.match(/<script>\n([\s\S]*?)<\/script>/)[1];

// Monta la página con un `fetch` controlado. `rutas` mapea
// "<METHOD> <path>" -> función que devuelve una Response simulada o lanza
// (para simular caída de red / TLS / CORS: `fetch` lanza TypeError).
function montar(rutas, { url = "https://landing.test/" } = {}) {
  const vc = new VirtualConsole();
  const errores = [];
  vc.on("jsdomError", (e) => errores.push(String(e?.stack || e)));

  const dom = new JSDOM(HTML.replace(/<script[\s\S]*?<\/script>/g, ""), {
    url,
    runScripts: "outside-only",
    virtualConsole: vc,
  });
  const win = dom.window;
  win.addEventListener("error", (e) => errores.push(String(e.error?.stack || e.message)));
  win.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
  if (!win.Element.prototype.scrollIntoView) win.Element.prototype.scrollIntoView = () => {};

  const llamadas = [];
  win.fetch = (u, opts = {}) => {
    const method = (opts.method || "GET").toUpperCase();
    const path = String(u).replace(/^https?:\/\/[^/]+/, "");
    llamadas.push({ url: String(u), method, path, opts });
    const h = rutas[`${method} ${path}`] ?? rutas[path];
    if (!h) return Promise.reject(new TypeError(`sin ruta simulada para ${method} ${path}`));
    try {
      const out = typeof h === "function" ? h() : h;
      if (out instanceof Error) return Promise.reject(out);
      const { status = 200, body = {} } = out;
      return Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        json: () => Promise.resolve(body),
      });
    } catch (e) {
      return Promise.reject(e);
    }
  };

  win.eval(pageScript);
  const $ = (id) => win.document.getElementById(id);
  return { win, $, llamadas, errores };
}

const tick = () => new Promise((r) => setTimeout(r, 0));

async function login(ctx, u = "demo", p = "demo") {
  ctx.$("u").value = u;
  ctx.$("p").value = p;
  ctx.$("login-form").dispatchEvent(new ctx.win.Event("submit"));
  await tick();
  await tick();
}

async function preguntar(ctx, texto = "¿aire en Retiro?") {
  ctx.$("input").value = texto;
  ctx.$("composer").dispatchEvent(new ctx.win.Event("submit"));
  await tick();
  await tick();
}

const textos = (ctx) => [...ctx.$("msgs").querySelectorAll(".msg")].map((m) => m.textContent);
const OK_HEALTH = { "GET /health": { status: 200 } };

test("FIL_92 · el endpoint se fija con ?api= sin editar el fichero", async () => {
  const ctx = montar(OK_HEALTH, { url: "https://landing.test/?api=http://localhost:9999/" });
  await login(ctx);
  assert.ok(
    ctx.llamadas.every((l) => l.url.startsWith("http://localhost:9999/")),
    `fetch no usó el ?api=: ${ctx.llamadas.map((l) => l.url).join(", ")}`,
  );
});

test("FIL_92 · login: ok / credenciales / backend caído / sin red", async () => {
  let ctx = montar({ "GET /health": { status: 200 } });
  await login(ctx);
  assert.equal(ctx.$("chat-screen").style.display, "flex");

  ctx = montar({ "GET /health": { status: 401 } });
  await login(ctx);
  assert.match(ctx.$("login-err").textContent, /incorrect/i);
  assert.notEqual(ctx.$("chat-screen").style.display, "flex");

  ctx = montar({ "GET /health": { status: 503 } });
  await login(ctx);
  assert.match(ctx.$("login-err").textContent, /no está disponible|unos minutos/i);

  ctx = montar({ "GET /health": () => new TypeError("Failed to fetch") });
  await login(ctx);
  assert.match(ctx.$("login-err").textContent, /conexión/i);
  assert.equal(ctx.$("login-btn").disabled, false, "el botón de login quedó bloqueado");
});

test("FIL_92 · chat: 500 muestra el código + Reintentar y no bloquea la UI", async () => {
  const ctx = montar({ ...OK_HEALTH, "POST /chat": { status: 500 } });
  await login(ctx);
  await preguntar(ctx);
  const err = ctx.$("msgs").querySelector(".msg.bot.error");
  assert.ok(err, "no apareció mensaje de error");
  assert.match(err.textContent, /\(500\)/);
  assert.ok(err.querySelector("button.retry"), "sin botón Reintentar");
  assert.equal(ctx.$("input").disabled, false, "el input quedó deshabilitado");
});

test("FIL_92 · chat: 429 se comunica como límite de uso, no como traza", async () => {
  const ctx = montar({ ...OK_HEALTH, "POST /chat": { status: 429 } });
  await login(ctx);
  await preguntar(ctx);
  assert.match(textos(ctx).join("\n"), /saturado|límite de uso/i);
});

test("FIL_92 · chat: respuesta vacía y caída de red tienen su propio mensaje", async () => {
  let ctx = montar({ ...OK_HEALTH, "POST /chat": { status: 200, body: { respuesta: null } } });
  await login(ctx);
  await preguntar(ctx);
  assert.match(textos(ctx).join("\n"), /no devolvió una respuesta/i);

  ctx = montar({ ...OK_HEALTH, "POST /chat": () => new TypeError("Failed to fetch") });
  await login(ctx);
  await preguntar(ctx);
  assert.match(textos(ctx).join("\n"), /conexión/i);
  assert.equal(ctx.$("input").disabled, false);
});

test("FIL_92 · Reintentar reenvía la última pregunta", async () => {
  let responder = { status: 500 };
  const ctx = montar({ ...OK_HEALTH, "POST /chat": () => responder });
  await login(ctx);
  await preguntar(ctx, "¿tráfico en Sol?");
  const nChatAntes = ctx.llamadas.filter((l) => l.path === "/chat").length;
  responder = { status: 200, body: { respuesta: "fluido" } };
  ctx.$("msgs").querySelector("button.retry").dispatchEvent(new ctx.win.Event("click"));
  await tick();
  await tick();
  const chatCalls = ctx.llamadas.filter((l) => l.path === "/chat");
  assert.equal(chatCalls.length, nChatAntes + 1, "Reintentar no volvió a llamar a /chat");
  assert.equal(JSON.parse(chatCalls.at(-1).opts.body).mensaje, "¿tráfico en Sol?");
  assert.match(textos(ctx).join("\n"), /fluido/);
});

test("FIL_92 · sin excepciones de página en ningún camino", async () => {
  const ctx = montar({ ...OK_HEALTH, "POST /chat": { status: 500 } });
  await login(ctx);
  await preguntar(ctx);
  assert.deepEqual(ctx.errores, []);
});
