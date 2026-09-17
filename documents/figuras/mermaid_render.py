"""Renderiza un diagrama Mermaid a PNG con Playwright + Chromium headless
(ya usados en el proyecto para QA de navegador real, ver VIC_32) y
mermaid.js vía CDN -- no hay Node/npx en esta instancia, así que no se usa
mermaid-cli. Salida: un PNG de alta resolución listo para insertar en la
memoria con `python-docx`.

    python -m documents.figuras.mermaid_render <entrada.mmd> <salida.png> [--width N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

_HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
  html,body{{margin:0;padding:0;background:#ffffff;}}
  #d{{display:inline-block;padding:24px;background:#ffffff;font-family:"Segoe UI",Arial,sans-serif;}}
</style>
</head><body>
<div id="d" class="mermaid">
{src}
</div>
<script>
  mermaid.initialize({{startOnLoad:true, theme:"neutral", themeVariables:{{fontSize:"16px"}}, flowchart:{{useMaxWidth:false}}, sequence:{{useMaxWidth:false}}}});
</script>
</body></html>
"""


def render(mmd_path: Path, out_path: Path, width: int = 1600) -> None:
    src = mmd_path.read_text(encoding="utf-8")
    html = _HTML.format(src=src)
    tmp_html = out_path.with_suffix(".render.html")
    tmp_html.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 200})
        page.goto(f"file://{tmp_html.resolve()}")
        page.wait_for_selector("#d svg", timeout=15000)
        # deja que mermaid termine de maquetar antes de medir/capturar
        page.wait_for_timeout(300)
        el = page.query_selector("#d")
        el.screenshot(path=str(out_path))
        browser.close()
    tmp_html.unlink(missing_ok=True)
    print(f"{out_path} ({out_path.stat().st_size / 1024:.0f} KB)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("entrada", type=Path)
    ap.add_argument("salida", type=Path)
    ap.add_argument("--width", type=int, default=1600)
    args = ap.parse_args()
    render(args.entrada, args.salida, args.width)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
