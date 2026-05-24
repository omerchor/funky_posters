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


def pdf_page_count(pdf_path: Path) -> int:
    data = pdf_path.read_bytes()
    # Find the largest /Count N in the PDF (top-level Pages dict)
    counts = [int(m) for m in re.findall(rb"/Count\s+(\d+)", data)]
    return max(counts) if counts else -1


async def export(html_path: Path, pdf_path: Path):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()

        # Viewport = A0 printable width at 96 dpi so vw units track correctly
        px_per_mm = 96 / 25.4
        printable_w_px = int((A0_W_MM - 2 * MARGIN_MM) * px_per_mm)  # ~3066
        printable_h_px = int((A0_H_MM - 2 * MARGIN_MM) * px_per_mm)  # ~4382
        await page.set_viewport_size({"width": printable_w_px, "height": printable_h_px})

        await page.goto(html_path.as_uri(), wait_until="networkidle")
        await page.evaluate("() => MathJax.startup.promise")

        # Measure in print-media mode so @media print styles are active
        await page.emulate_media(media="print")
        content_h_px = await page.evaluate("() => document.body.scrollHeight")
        scale = min(1.0, printable_h_px / content_h_px)
        print(f"Content height: {content_h_px}px  initial scale: {scale:.4f}")

        # Iteratively tighten scale until the PDF is a single page
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
