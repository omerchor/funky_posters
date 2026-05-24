#!/usr/bin/env python3
"""Export a poster HTML file to a single-page A0 PDF, waiting for MathJax."""

import re
import sys
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

# A0 in mm
A0_W_MM = 841
A0_H_MM = 1189
MARGIN_MM = 15

# JavaScript injected before PDF generation.
# Chromium's PDF renderer ALWAYS rasterises CSS backgrounds (gradients and even
# SVG data-URIs) at screen DPI, so they look pixelated at A0 scale.  The only
# way to get crisp, resolution-independent dots is to inject actual inline SVG
# elements into the DOM — those ARE preserved as vectors in the PDF output.
#
# Strategy:
#   1. Clear background-image on each target element.
#   2. Insert an absolutely-positioned <svg> as its first child (z-index: 0).
#      The SVG uses a <pattern> (userSpaceOnUse, coordinates = CSS px) so the
#      dots tile at the correct physical size.
#   3. Lift every other direct child to z-index: 1 so they sit above the SVG.
_INJECT_VECTOR_DOTS_JS = r"""
() => {
    const PX_PER_CM = 96 / 2.54;   // CSS pixels per cm at standard 96 DPI

    /**
     * Replace the CSS background-image dot pattern on every element matching
     * `selector` with a fully-vector inline SVG that renders identically.
     *
     * @param {string}  selector      - CSS selector for target elements
     * @param {string}  fill          - dot fill colour (any CSS colour string)
     * @param {number}  fillOpacity   - dot fill-opacity [0-1]
     * @param {number}  rFraction     - dot radius as a fraction of tile size
     * @param {number}  tileCm        - tile (grid cell) size in centimetres
     */
    function injectDotBg(selector, fill, fillOpacity, rFraction, tileCm) {
        const tilePx = tileCm * PX_PER_CM;
        const r      = tilePx * rFraction;
        const cx     = tilePx / 2;

        document.querySelectorAll(selector).forEach(el => {
            // Remove the rasterised CSS background; keep background-color.
            el.style.setProperty('background-image', 'none', 'important');

            // Ensure the element is a positioning context for the absolute SVG.
            if (getComputedStyle(el).position === 'static')
                el.style.position = 'relative';

            // Lift existing direct children above the SVG (z-index: 0) layer.
            for (const child of el.children) {
                if (child.dataset.bgSvg) continue;
                const cs = getComputedStyle(child);
                if (cs.position === 'static') child.style.position = 'relative';
                if (!child.style.zIndex || parseInt(child.style.zIndex) < 1)
                    child.style.zIndex = '1';
            }

            // Build the inline SVG with a <pattern> instead of a CSS background.
            const id  = 'dp' + Math.random().toString(36).slice(2, 10);
            const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.dataset.bgSvg = '1';
            svg.setAttribute('aria-hidden', 'true');
            svg.style.cssText = [
                'position:absolute', 'inset:0', 'width:100%', 'height:100%',
                'z-index:0', 'pointer-events:none', 'overflow:hidden',
            ].join(';');

            svg.innerHTML =
                `<defs>` +
                  `<pattern id="${id}" patternUnits="userSpaceOnUse"` +
                           ` width="${tilePx}" height="${tilePx}">` +
                    `<circle cx="${cx}" cy="${cx}" r="${r}"` +
                            ` fill="${fill}" fill-opacity="${fillOpacity}"/>` +
                  `</pattern>` +
                `</defs>` +
                `<rect width="100%" height="100%" fill="url(#${id})"/>`;

            el.insertBefore(svg, el.firstChild);
        });
    }

    // ── poster canvas: black dots, 1.5 cm tile, r = 15 % of tile ──────────
    injectDotBg('.poster-canvas',                      'black',   1.00, 0.15, 1.5);

    // ── scaffold mesh cells: 1.3 cm tile, r = 25 % of tile ────────────────
    injectDotBg('.scaffold-cell.pink-mesh',            '#ff3377', 0.22, 0.25, 1.3);
    injectDotBg('.scaffold-cell.cyan-mesh',            '#00d8ff', 0.22, 0.25, 1.3);
    injectDotBg('.scaffold-cell.amber-mesh',           '#ffcc00', 0.28, 0.25, 1.3);

    // ── equation-slab dot overlays: 1.1 cm tile, r = 25 % of tile ─────────
    injectDotBg('.equation-slab-feature.slab-cyan',    '#00d8ff', 0.38, 0.25, 1.1);
    injectDotBg('.equation-slab-feature.slab-magenta', '#ff3377', 0.38, 0.25, 1.1);
    injectDotBg('.equation-slab-feature.slab-amber',   '#ffcc00', 0.48, 0.25, 1.1);
}
"""


def pdf_page_count(pdf_path: Path) -> int:
    data = pdf_path.read_bytes()
    counts = [int(m) for m in re.findall(rb"/Count\s+(\d+)", data)]
    return max(counts) if counts else -1


async def export(html_path: Path, pdf_path: Path):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context()
        page = await context.new_page()

        # Viewport = A0 printable width at 96 dpi so vw units track correctly.
        px_per_mm = 96 / 25.4
        printable_w_px = int((A0_W_MM - 2 * MARGIN_MM) * px_per_mm)  # ~3066
        printable_h_px = int((A0_H_MM - 2 * MARGIN_MM) * px_per_mm)  # ~4382
        await page.set_viewport_size({"width": printable_w_px, "height": printable_h_px})

        await page.goto(html_path.as_uri(), wait_until="networkidle")
        await page.evaluate("() => MathJax.startup.promise")

        # Switch to print-media so @media print rules are active before we
        # measure content height and inject the vector backgrounds.
        await page.emulate_media(media="print")

        # Replace all rasterised CSS dot-pattern backgrounds with inline SVG
        # <pattern> elements that Chromium preserves as vectors in the PDF.
        await page.evaluate(_INJECT_VECTOR_DOTS_JS)

        content_h_px = await page.evaluate("() => document.body.scrollHeight")
        scale = min(1.0, printable_h_px / content_h_px)
        print(f"Content height: {content_h_px}px  initial scale: {scale:.4f}")

        # Iteratively tighten scale until the PDF is a single page.
        while True:
            await page.pdf(
                path=str(pdf_path),
                width=f"{A0_W_MM}mm",
                height=f"{A0_H_MM}mm",
                print_background=True,
                scale=scale,
                margin={k: f"{MARGIN_MM}mm" for k in ("top", "bottom", "left", "right")},
            )
            pages = pdf_page_count(pdf_path)
            print(f"  scale={scale:.4f}  pages={pages}")
            if pages <= 1:
                break
            scale -= 0.02

        await browser.close()
        print(f"Saved: {pdf_path}  (scale={scale:.4f})")


if __name__ == "__main__":
    html = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "projects/curl_forces/poster.html")
    pdf = html.with_suffix(".pdf")
    asyncio.run(export(html.resolve(), pdf.resolve()))
