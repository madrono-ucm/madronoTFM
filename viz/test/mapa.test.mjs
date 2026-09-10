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

// Monta la página en un DOM real con deck.gl / maplibre / fetch simulados y
// espera a que resuelva la carga. Devuelve `{ win, errors, $ }`.
// `MapboxOverlay.setProps` ejecuta de verdad los accessors de la capa de
// nodos (color/altura) sobre una muestra de índices: así los tests ven un
// `throw` dentro de `nodeColor`/`nodeElev` (que con el stub plano pasaba
// desapercibido) y el coste O(n²) de FIL_88 si se pierde la memoización.
async function montar() {
  const vc = new VirtualConsole();
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
  const ejercitarAccessors = (layers) => {
    for (const L of layers || []) {
      if (L?.id !== "nodes" || !Array.isArray(L.data)) continue;
      const n = L.data.length;
      const muestra = [0, 1, (n / 2) | 0, n - 2, n - 1].filter((i) => i >= 0 && i < n);
      for (const i of muestra) {
        L.getPosition?.(L.data[i]);
        L.getFillColor?.(L.data[i]);
        L.getElevation?.(L.data[i]);
      }
    }
  };
  win.deck = {
    ScatterplotLayer: LayerStub,
    ColumnLayer: LayerStub,
    LineLayer: LayerStub,
    ArcLayer: LayerStub,
    GeoJsonLayer: LayerStub,
    PathLayer: LayerStub,
    TextLayer: LayerStub,
    MapboxOverlay: class {
      constructor(p) { this.props = p || {}; }
      setProps(p) { Object.assign(this.props, p); if (p && p.layers) ejercitarAccessors(p.layers); }
      onAdd() { return win.document.createElement("div"); }
      onRemove() {}
    },
  };
  class MapStub {
    constructor(o) { this._o = o || {}; this._h = {}; this._z = o?.zoom ?? 10.6; this._p = o?.pitch ?? 0; this._b = o?.bearing ?? 0; }
    addControl() { return this; }
    removeControl() { return this; }
    on(ev, cb) { (this._h[ev] = this._h[ev] || []).push(cb); if (ev === "load") setTimeout(cb, 0); return this; }
    once(ev, cb) { setTimeout(cb, 0); return this; }
    off() { return this; }
    _fire(ev) { (this._h[ev] || []).forEach((cb) => cb()); }
    getCenter() { return { lng: -3.7, lat: 40.43 }; }
    getZoom() { return this._z; }
    getPitch() { return this._p; }
    getBearing() { return this._b; }
    isStyleLoaded() { return true; }
    setStyle() { setTimeout(() => this._fire("styledata"), 0); return this; }
    fitBounds() { this._fire("move"); return this; }
    easeTo(o) { if (o?.pitch != null) this._p = o.pitch; if (o?.bearing != null) this._b = o.bearing; this._fire("move"); return this; }
  }
  win.maplibregl = { Map: MapStub, NavigationControl: class {} };
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
  return { win, errors, $ };
}

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

test("FIL_56 · disparar todos los controles no lanza ninguna excepción", async () => {
  const { win, errors, $ } = await montar();

  const before = errors.length;
  const click = (el) => el && el.click();
  const fire = (el, type) => el && el.dispatchEvent(new win.Event(type));

  // FIL_77: barra lateral -> abrir cada sección (una visible a la vez) y
  // dejar "Historia" abierta al final.
  win.document.querySelectorAll("#rail button").forEach(click);
  win.document.querySelector('#rail button[data-sec="historia"]').click();

  win.document.querySelectorAll(".met").forEach(click); // 4 métricas base + 3 virtuales
  win.document.querySelectorAll(".pf").forEach(click); // 9 perfiles de sensibilidad
  win.document.querySelectorAll(".es").forEach(click); // escala lineal / bandas
  win.document.querySelectorAll(".hz").forEach(click); // 4 horizontes
  win.document.querySelectorAll(".day").forEach(click); // 3 días
  win.document.querySelectorAll(".rp").forEach(click); // puntos / auto / barras
  win.document.querySelectorAll("#hist-caps button").forEach(click); // recorrido guiado: los 6 capítulos
  click($("hist-prev"));
  click($("hist-next"));
  click($("hist-auto")); // arranca la animación…
  click($("hist-auto")); // …y la para, para no dejar timers colgando
  win.document.querySelectorAll("#chat-sug button").forEach(click); // sugerencias del chat (fetch mockeado -> falla, degrada)
  click($("chat-send"));
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
  for (const opt of [...$("basemap").options].map((o) => o.value)) { // voyager/positron/dark-matter/ninguno
    $("basemap").value = opt;
    fire($("basemap"), "change");
  }
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
  // FIL_88: los accessors de la capa de nodos se ejecutaron de verdad
  // (montar() los llama); si alguna combinación métrica/escala/repr/perfil
  // rompiera `nodeColor`/`nodeElev`, `render()` lo captaría y mostraría el
  // banner. No debe estar visible tras un recorrido sano.
  assert.equal($("err").style.display, "none", `#err visible: ${$("err").textContent}`);
});

test("FIL_88 · metricArr memoiza el vector de perfil/dosis (no O(n²) por render)", async () => {
  const { win } = await montar();
  // salud (perfil): sin memo, `metricArr()` reconstruía el array 1798·2
  // veces por render. Con memo, dos llamadas seguidas con el mismo estado
  // devuelven la MISMA referencia.
  win.document.querySelector('.pf[data-p="asma_epoc"]').click();
  assert.equal(win.metricArr(), win.metricArr(), "salud_perfil no está memoizado");
  win.document.querySelector('.met[data-m="dosis_o3"]').click();
  assert.equal(win.metricArr(), win.metricArr(), "dosis_o3 no está memoizado");
  // y cambiar de hora invalida la caché (valores distintos)
  const antes = win.metricArr();
  win.document.querySelector('.pf[data-p="general"]').click();
  assert.notEqual(win.metricArr(), antes, "la caché no se invalidó al cambiar de perfil");
});

test("FIL_88 · un throw dentro del render no congela el mapa (banner + recuperación)", async () => {
  const { win, $ } = await montar();
  const layersOk = win.layers;
  win.layers = () => { throw new Error("fallo simulado en layers()"); };
  win.render();
  assert.equal($("err").style.display, "block", "el banner de error no apareció");
  assert.match($("err").textContent, /No se pudo actualizar el mapa/);
  // el siguiente cambio vuelve a intentarlo y, ya sano, se recupera
  win.layers = layersOk;
  win.render();
  assert.equal($("err").style.display, "none", "el banner no se ocultó tras recuperar");
});

test("FIL_88 · «bandas OMS·UE» tiñe de verdad las métricas de dosis", async () => {
  const { win, $ } = await montar();
  win.document.querySelector('.met[data-m="dosis_o3"]').click();
  win.document.querySelector('.es[data-e="bandas"]').click();
  assert.notEqual($("leg-bandas").style.display, "none", "la leyenda de bandas sigue oculta con dosis_o3");
  assert.equal($("leg").style.display, "none", "la leyenda de degradado no se ocultó");
});

test("FIL_88 · los capítulos no se filtran estado entre sí (escala vuelve a lineal)", async () => {
  const { win } = await montar();
  const caps = win.document.querySelectorAll("#hist-caps button");
  caps[1].click(); // cap. 2: dosis_o3 + bandas
  assert.equal(win.document.querySelector('.es[data-e="bandas"]').classList.contains("on"), true);
  caps[5].click(); // cap. 6: métrica "salud" (que sí tiene umbral) — no debe heredar "bandas"
  assert.equal(
    win.document.querySelector('.es[data-e="lineal"]').classList.contains("on"),
    true,
    "el cap. 6 heredó escala:bandas del cap. 2",
  );
});
