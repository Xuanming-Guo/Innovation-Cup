# Browser QA evidence

This folder archives the repository user's 2026-09-26 desktop Chrome review of
the local synthetic replay at `127.0.0.1:8765`. The eleven PNGs show the judge
overview plus the stored manager, Security and Delivery projections. Their exact
scope and limitations are recorded in `manifest.json`.

This is evidence that the pre-inspector replay rendered in a real browser and
that the loopback service was reachable. It is not a native Tauri test, a live
connector test, a product result or an access-control test. The development POV
selector explicitly has no authentication claim.

The company/graph inspector and supporting portfolio scenario were added after
these images. They have automated data, syntax and interaction-logic coverage,
but require a fresh desktop and narrow-viewport browser pass before the updated
UI can close the browser portion of §13.1.

Expected rerun checklist:

1. Open the company/graph inspector and confirm all 25 employee profiles can be
   searched, filtered and paged.
2. Switch to the graph, inspect naive A and B, and verify node selection plus
   impacted/all-considered scope switching.
3. Run or serve `A B portfolio`, select `portfolio`, and verify the graph reports
   12 owner changes, 23 contacts, four teams and 80 considered tasks after B.
4. Select manager, Security and Delivery POVs; verify their visible task graphs
   contain only the corresponding stored projection.
5. Repeat the key path at a narrow viewport and archive one screenshot.
