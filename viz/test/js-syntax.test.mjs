// FIL_91 — `node --check` del JavaScript embebido de TODAS las páginas
// generadas del frontend, no solo del mapa (FIL_57 solo cubría
// `viz/mapa/index.html`). Un `}` de más en cualquiera de ellas rompe la
// página en el navegador sin que ningún test de Python lo vea.

import { test } from "node:test";
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { jsInline } from "../extraer_js.mjs";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

// Página -> globales que espera del CDN (para que `node --check` no falle por
// `no-undef` -- solo comprueba sintaxis, no ejecuta).
const PAGINAS = {
  "viz/mapa/index.html": ["deck", "maplibregl"],
  "viz/grafo_explorador_live.html": ["maplibregl"],
  "viz/grafo_explorador.html": ["maplibregl"],
  "web/index.html": [],
};

for (const [rel, globales] of Object.entries(PAGINAS)) {
  test(`FIL_91 · ${rel}: el <script> embebido es sintácticamente válido`, () => {
    const html = readFileSync(join(RAIZ, rel), "utf8");
    const dir = mkdtempSync(join(tmpdir(), "fe-js-"));
    const file = join(dir, "inline.js");
    const preludio = globales.length ? `const ${globales.map((g) => `${g} = {}`).join(", ")};\n` : "";
    writeFileSync(file, preludio + jsInline(html));
    execFileSync(process.execPath, ["--check", file]);
  });
}
