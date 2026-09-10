// Utilidad compartida por los tests de frontend (FIL_57 / FIL_91): saca el
// JavaScript embebido de una página generada.
//
// Los `<script src=...>` son los CDN (deck.gl, maplibre); el resto es el
// código propio de la página, que es lo que queremos pasar por
// `node --check` o cargar en jsdom.

/** Concatena el contenido de todos los `<script>` SIN atributo `src`. */
export function jsInline(html) {
  const norm = html.replace(/\r\n/g, "\n");
  const bloques = [
    ...norm.matchAll(/<script(?![^>]*\bsrc=)[^>]*>\n?([\s\S]*?)<\/script>/g),
  ].map((m) => m[1]);
  if (!bloques.length) throw new Error("la página no tiene ningún <script> inline");
  return bloques.join("\n;\n");
}

/** El HTML sin ningún `<script>` (para inspeccionar solo el marcado estático). */
export function sinScripts(html) {
  return html.replace(/<script[\s\S]*?<\/script>/g, "");
}
