# Scenario handoff verification

Deliverable: `../scenario-facts-for-teammate.docx`; editable content: `../scenario-facts-for-teammate.md`.

Verified against existing archived run `benchmark-43329a535133469887a6e9517b1d8977` and the scenario definition. No simulation or product execution, source-fixture changes, or Git mutations were performed.

Checks completed:

- `python3 -B scripts/check_repository.py` using the packaged Codex Python runtime: **PASS**, “Repository contract checks passed.” The check excludes `simulation/`.
- Read-only assertions against archived JSON: **PASS**, all nine main employee names/IDs, all four team names/IDs, original and revised deadlines, and exact before/after conflict slots.
- Relative Markdown source links: **PASS**, all targets exist.
- DOCX structure: **PASS**, explicit 9360-DXA tables and 120-DXA indents.
- Packaged `render_docx.py` with this folder’s `fonts.conf`: **PASS**, two populated pages; all 14 occurrences of 架空 preserved in PDF text. Earlier renders lacked CJK fonts and were replaced.
- Opened and visually inspected both final page images: **PASS**, legible text, complete Japanese labels, clear tables, no blank pages or clipped/overlapping content.

The original render evidence is in `cjk-render/`. Its PDF and PNGs are internal QA artifacts. The Word document is the requested deliverable.

## Follow-up: distinct names for the two Aoi employees

Updated the handoff to use **Emi Tanaka (e0000)** and **Haruto Sato (e0010)**. Page 2 explicitly maps these story names to the original archived display labels. The simulation generator and historical runs remain unchanged.

- New-name/ID mapping, unchanged archived labels and relative links: **PASS**.
- Re-ran `python3 -B scripts/check_repository.py`: **PASS**.
- Rebuilt and rendered the revised Word document: **PASS**, two pages, both new names and all 12 remaining Japanese marker occurrences present.
- Inspected both revised page images: **PASS**, complete and legible.

Current render evidence is in `renamed-render/`.

Runtime: `/Users/sophiaji/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`.

Rebuild with `build_document.py`. Render with the Documents skill’s `render_docx.py`, setting `FONTCONFIG_FILE` to the absolute path of this folder’s `fonts.conf`; this permits the bundled renderer to read existing system Japanese fonts. No fonts were installed.

## Follow-up: ALTO product name

Updated the generator's running header and author metadata to **ALTO**, then rebuilt
`scenario-facts-for-teammate.docx`. The Markdown scenario facts are unchanged.

- Rebuilt with the packaged Python runtime and rendered with `render_docx.py` plus
  the existing `fonts.conf`: **PASS**, two pages.
- Inspected both page images: **PASS**, ALTO header, complete tables and readable labels.
- Pixel comparison against `renamed-render/`: **PASS**, only header pixels changed on
  each page; body layout is identical.
- DOCX XML checks: **PASS**, no previous product name, both story names retained and
  all 12 Japanese marker occurrences preserved.

Current render evidence is in `alto-render/`. Prior QA renders remain historical evidence.
