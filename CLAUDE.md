# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A collection of HTML-based academic poster templates with a neo-brutalist / pop-art aesthetic. Posters render math via MathJax (loaded from CDN) and are designed to be printed or displayed in a browser.

## Template anatomy (`templates/comic_template.html`)

- **Header** (`#poster-header`) — title, author names (`.meta-mesh`), and affiliation (`.affiliation-panel`).
- **Dynamic stack** (`#interactive-stack`) — ordered sequence of alternating `.scaffold-cell` panels and `.equation-slab-feature` slabs. Cells come in four style variants: `cyan-mesh`, `pink-mesh`, `amber-mesh`, `solid-yellow`.
- **Footer** (`#poster-footer`) — references and contact info.
- **Auto-layout script** — on `DOMContentLoaded`, iterates over stack children to assign `data-index` attributes to cells and applies alternating CSS transforms (tilt, skew, translateY) to give the stacked-cards look.

## Design system (CSS variables in `:root`)

| Variable | Value | Role |
|---|---|---|
| `--ink-black` | `#000000` | borders, text |
| `--paper-cream` | `#faf7f0` | panel backgrounds |
| `--pop-pink` | `#ff3377` | accent |
| `--pop-cyan` | `#00d8ff` | accent |
| `--pop-yellow` | `#ffcc00` | accent / solid panels |
| `--thick-border` | `6px solid black` | universal border style |
| `--block-shadow-large` | `20px 20px 0px black` | card shadow |

## MathJax

Inline math: `$...$` or `\(...\)`. Display math: `$$...$$` or `\[...\]`. The body tag carries `class="tex2jax_process"` so MathJax processes the whole document.

## Viewing / printing

Open any `.html` file directly in a browser — no build step. Use the browser's Print dialog for physical output; the `@media print` block strips shadows and resets padding.
