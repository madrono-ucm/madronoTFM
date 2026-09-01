// Tests funcionales del mapa animado publicado (`viz/mapa/index.html`).
//
// Cubren dos huecos que los tests de `tests/test_mapa_animado.py` no ven,
// porque aquellos solo comprueban presencia de subcadenas en el HTML:
//
//   - FIL_56: cargar el HTML en un DOM real (jsdom), con deck.gl / maplibre
//     / fetch simulados, y disparar TODOS los controles. Falla si `render()`
//     lanza — habría cazado el `TypeError` de FIL_55 (métricas de perfil /
//     dosis rompían el panel de resumen).
//   - FIL_57: sintaxis del `<script>` generado (`node --check`) y que cada
//     `getElementById("x")` tenga su `id="x"` en el HTML (habría cazado el
//     `onClick` perdido de FIL_47).
//
// Ejecutar: `cd viz && npm ci && npm test`.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM, VirtualConsole } from "jsdom";

const MAPA = join(dirname(fileURLToPath(import.meta.url)), "..", "mapa");
const html = readFileSync(join(MAPA, "index.html"), "utf8").replace(/\r\n/g, "\n");
const files = Object.fromEntries(
  ["meta.json", "data.json", "weather.json", "rutas.json"].map((f) => [
    f,
    JSON.parse(readFileSync(join(MAPA, f), "utf8")),
  ]),
);
// El único <script> sin atributos (los del CDN son <script src=...>).
const pageScript = html.match(/<script>\n([\s\S]*?)<\/script>/)[1];

test("FIL_57 · el <script> generado es sintácticamente válido (node --check)", () => {
  const dir = mkdtempSync(join(tmpdir(), "mapa-js-"));
  const file = join(dir, "inline.js");
  // deck / maplibregl son globales que la página espera del CDN; con
  // declararlos basta para que `node --check` no falle por `no-undef`.
  writeFileSync(file, "const deck = {}, maplibregl = {};\n" + pageScript);
  execFileSync(process.execPath, ["--check", file]);
});

test("FIL_57 · todo getElementById('x') tiene su id='x' en el HTML", () => {
  const referenced = new Set(
    [...html.matchAll(/getElementById\(["']([^"']+)["']\)/g)].map((m) => m[1]),
  );
  const defined = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]));
  const faltan = [...referenced].filter((id) => !defined.has(id));
  assert.deepEqual(faltan, [], `getElementById sin id en el HTML: ${faltan.join(", ")}`);
});

test("FIL_56 · disparar los 51 controles no lanza ninguna excepción", async () => {
  const vc = new VirtualConsole(); // silencia el volcado de jsdom; trazamos aparte
  const errors = [];
  vc.on("jsdomError", (e) => errors.push("jsdomError: " + (e?.stack || e)));

  const dom = new JSDOM(html.replace(/<script[\s\S]*?<\/script>/g, ""), {
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole: vc,
  });
  const win = dom.window;
  win.addEventListener("error", (e) => errors.push("window error: " + (e.error?.stack || e.message)));

  class LayerStub {
    constructor(props) {
      Object.assign(this, props);
    }
  }
  win.deck = {
    DeckGL: class {
      constructor(p) {
        this.props = p || {};
        this.deck = { width: 1200, height: 800 };
      }
      setProps(p) {
        Object.assign(this.props, p);
      }
    },
    ScatterplotLayer: LayerStub,
    ColumnLayer: LayerStub,
    LineLayer: LayerStub,
    ArcLayer: LayerStub,
    GeoJsonLayer: LayerStub,
    PathLayer: LayerStub,
    TextLayer: LayerStub,
    WebMercatorViewport: class {
      fitBounds() {
        return { longitude: -3.7, latitude: 40.43, zoom: 11 };
      }
    },
  };
  win.maplibregl = {};
  win.fetch = (url) => {
    const key = String(url).replace("./", "");
    return key in files
      ? Promise.resolve({ ok: true, json: () => Promise.resolve(files[key]) })
      : Promise.reject(new Error("sin stub para " + url));
  };

  win.eval(pageScript);
  await new Promise((r) => setTimeout(r, 150)); // deja resolver el Promise.all de carga

  const $ = (id) => win.document.getElementById(id);
  assert.notEqual($("titulo-sub").textContent, "—", "la carga inicial no completó render()");

  const before = errors.length;
  const click = (el) => el && el.click();
  const fire = (el, type) => el && el.dispatchEvent(new win.Event(type));

  win.document.querySelectorAll(".met").forEach(click); // 4 métricas base + 3 virtuales
  win.document.querySelectorAll(".pf").forEach(click); // 9 perfiles de sensibilidad
  win.document.querySelectorAll(".es").forEach(click); // escala lineal / bandas
  win.document.querySelectorAll(".hz").forEach(click); // 4 horizontes
  win.document.querySelectorAll(".day").forEach(click); // 3 días
  win.document.querySelectorAll(".rp").forEach(click); // puntos / auto / barras
  click($("ghost"));
  click($("ghost"));
  $("hour").value = "23";
  fire($("hour"), "input");
  $("hour").value = "0";
  fire($("hour"), "input");
  click($("v3d"));
  click($("v2d"));
  click($("fit"));
  click($("clean"));
  click($("clean"));
  ["l-distr", "l-hitos", "l-ejes", "l-parques", "l-tex", "l-idw"].forEach((id) => {
    $(id).checked = !$(id).checked;
    fire($(id), "change");
  });
  click($("tab-a"));
  click($("tab-d"));
  const od = $("r-od");
  if (od.options.length > 1) {
    od.value = "0";
    fire(od, "change");
  }
  const pf = $("r-perfil");
  if (pf.options.length > 1) {
    pf.selectedIndex = 1;
    fire(pf, "change");
  }
  od.value = "-1";
  fire(od, "change");
  click($("play"));
  click($("play"));

  assert.deepEqual(errors.slice(before), [], "excepciones al disparar los controles");
});
