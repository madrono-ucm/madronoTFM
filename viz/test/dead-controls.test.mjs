// FIL_91 — "ningún control muerto": todo <button>/<input>/<select> del
// marcado ESTÁTICO de una página del frontend tiene que estar cableado a
// algo en su JavaScript. Caza el caso que reportó el usuario ("botones que
// no hacen nada") de forma barata y robusta, sin montar la página entera.
//
// Es un chequeo estático (no ejecuta la página): comprueba que el control
// es *alcanzable* desde el JS por al menos un selector -- su `id`, una de
// sus clases, un `data-*`, un `onclick=` inline, o ser el submit de un
// <form> con manejador. No prueba que el handler haga lo correcto (de eso
// se encarga el arnés jsdom de `mapa.test.mjs`), pero un botón sin ninguna
// vía de cableado lo detecta seguro.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";
import { jsInline, sinScripts } from "../extraer_js.mjs";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

// Excepciones documentadas: controles decorativos o cuyo cableado no es
// detectable estáticamente. Cada entrada necesita un motivo.
const CONOCIDOS = {
  // (ninguna por ahora)
};

const PAGINAS = ["viz/mapa/index.html", "viz/grafo_explorador_live.html", "web/index.html"];

const camel = (s) => s.replace(/-([a-z])/g, (_, c) => c.toUpperCase());

function descripcion(el) {
  const cls = [...el.classList].map((c) => "." + c).join("");
  const data = [...el.attributes]
    .filter((a) => a.name.startsWith("data-"))
    .map((a) => `[${a.name}]`)
    .join("");
  return `${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}${cls}${data}`;
}

function estaCableado(el, js) {
  if (el.id && (js.includes(`"${el.id}"`) || js.includes(`'${el.id}'`) || js.includes(`#${el.id}`))) {
    return true;
  }
  for (const c of el.classList) {
    if (js.includes(`.${c}`) || js.includes(`"${c}"`) || js.includes(`'${c}'`)) return true;
  }
  for (const attr of el.attributes) {
    if (!attr.name.startsWith("data-")) continue;
    const k = attr.name.slice(5);
    if (js.includes(attr.name) || js.includes(`[data-${k}`) || js.includes(`dataset.${camel(k)}`)) {
      return true;
    }
  }
  if (el.hasAttribute("onclick")) return true;
  // submit / reset de un <form>: cableado si el form tiene manejador
  const tipo = (el.getAttribute("type") || "").toLowerCase();
  if (tipo === "submit" || tipo === "reset" || el.tagName === "BUTTON") {
    const form = el.closest("form");
    if (form && (js.includes("addEventListener(\"submit\"") || js.includes("addEventListener('submit'") || js.includes("onsubmit"))) {
      if (!form.id || js.includes(`"${form.id}"`) || js.includes(`'${form.id}'`)) return true;
    }
  }
  return false;
}

for (const rel of PAGINAS) {
  test(`FIL_91 · ${rel}: ningún control sin cablear`, () => {
    const html = readFileSync(join(RAIZ, rel), "utf8");
    const js = jsInline(html);
    const { document } = new JSDOM(sinScripts(html)).window;
    const permitidos = CONOCIDOS[rel] || [];

    const huerfanos = [];
    for (const el of document.querySelectorAll("button, input, select")) {
      const d = descripcion(el);
      if (permitidos.includes(d)) continue;
      if (!estaCableado(el, js)) huerfanos.push(d);
    }
    assert.deepEqual(huerfanos, [], `controles sin ninguna vía de cableado en el JS: ${huerfanos.join(", ")}`);
  });
}
