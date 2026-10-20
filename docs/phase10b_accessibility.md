# Phase 10B: focused accessibility review

Review date: October 20, 2026. This is a **WCAG 2.2 AA-oriented review, not a
conformance certification**. [WCAG 2.2](https://www.w3.org/TR/WCAG22/) is the reference.
Financial calculations, scoring policies and inference validation were preserved.

## Confirmed issues and fixes

| Finding | Evidence | Correction |
|---|---|---|
| Section headings skipped from h1 to h3 | axe `heading-order` on Home; source review of other pages | Top-level sections use native h2; nested AI evidence retains h3. Existing heading assertions were updated to verify the semantic level. |
| Light success banners and positive deltas had insufficient text contrast | axe reported ratios 4.32:1 and 4.09:1 against the 4.5:1 normal-text target | Explicit dark-green/pale-green pairs; negative deltas use a dark-red/pale-red pair. Wording, signs and financial meaning stay intact. |
| Error feedback had insufficient contrast | Expanded invalid-plan scan reported 4.37:1 | Explicit dark-red text on a pale-red error surface. |
| Native table headers were too faint | Expanded chart-data scan reported 4.27:1 | Dark-slate headers on a pale-slate surface, in both themes. |
| Charts relied on graphical interaction | Inspection found no explicit text/data alternative | Every chart has descriptive `alt` text and an adjacent Chart data expander with a native HTML table of the plotted source values, including labels and reference lines. Histogram tables identify observations rather than inventing bin counts. |
| Canvas-based transaction grids alone are insufficient alternatives | Source review | Additional native HTML tables for filtered transactions and unusual-activity explanations. Existing interactive grids and exports remain available. |
| Native tables interpreted transaction text as Markdown | A harmless localhost-only fixture created an image and link before correction | Escape presentation text in native tables so descriptions/categories remain literal and cannot trigger image loads. Numeric values and original frames remain unchanged. |
| Enlarged metric text overlapped adjacent cards | Actual 200% root-font emulation screenshot and four overflowing KPI values | Allow nested metric paragraphs and labels to wrap; remove the forced single-line label height; let metric columns reflow to fewer cards per row as text grows. |
| Scenario error did not name its input | Entering `nan` in Emergency expense produced only a generic finite-number error | Validation feedback now names the relevant visible control, omits submitted values, and retains alert semantics and blocked partial results. |
| Focus styles did not cover every native control type | Source review | Visible 3px outline on focus-visible elements, with a light-teal dark-mode outline. |
| No explicit reduced-motion accommodation | Source review | Suppress CSS transitions/animations when the user requests reduced motion. Navigation already scrolls instantly. This is an additional comfort measure, not a claim about every animation inside Plotly. |
| Scenario line/heatmap palette needed stronger nontext/text contrast | Palette review | Deeper violet scenario line; pale heatmap surfaces with explicit dark count text. Dashed/solid lines, names and numeric tables provide meaning beyond color. |

## Executed checks

- Pinned **axe-core 4.11.0**, npm SHA-512 package integrity verified; used only from
  ignored `var/phase10b/vendor/`. No runtime dependency or paid audit service added.
- All **nine views × desktop/mobile × light/dark = 36 rendered page combinations**
  scanned for WCAG A/AA/2.1 AA/2.2 AA tags and axe best practices. Final scans found
  zero automated violations in these tested page states.
- Expanded chart, search-empty and invalid-plan states separately scanned. A further
  **12 expanded light/dark states** cover cash settings, chart data, transaction
  tables, unusual-activity tables, custom-plan controls and invalid-plan feedback.
- Actual CDP Tab and Enter events moved Home → Explore → Transactions, with a 3px
  visible outline. The collapsed mobile sidebar opened with keyboard Enter.
- Chromium's accessibility tree exposed the chart description, a native data table,
  labeled controls and h1/h2 headings. Invalid-plan feedback exposed `role=alert`.
- 720px and 320px CSS viewport reflow checks showed no page-level horizontal
  overflow or clipped KPI values in Plan. These emulate reduced CSS viewport sizes;
  **native browser menu zoom was not tested**.
- 200% root-font scaling was exercised and the confirmed KPI overlap corrected.
  This is not a substitute for testing every browser's text-size and zoom settings.
- Reduced-motion media emulation activated the override; the inspected button's
  transition duration was 0.00001 seconds.
- Computed heading/caption/primary-button samples met their respective targets in
  the tested themes. axe still marked some Plotly contrast checks **incomplete**;
  “zero violations” does not mean those checks passed.
- Genuine viewport screenshots were captured. Representative desktop Home, mobile
  Plan and dark AI Assistant images were inspected directly, along with the enlarged
  KPI defect. Automated layout checks covered all nine views; this is not a claim
  that a human reviewed every pixel of every capture.

Two-dimensional charts and data tables can legitimately need horizontal scrolling;
ordinary surrounding content should reflow. See the
[W3C reflow explanation](https://www.w3.org/WAI/WCAG21/Understanding/reflow).

## Remaining manual work

No NVDA, JAWS or VoiceOver session, physical mobile device test, participant study,
native browser 200%/400% zoom run, complete target-size inventory, or comprehensive
manual chart/hover/disabled-control contrast audit has been performed. Test focus
restoration and announcement order after Streamlit reruns with a screen reader;
inspect whether validation feedback needs additional field association. Native
HTML alternatives improve access but do not certify every third-party grid/chart.

Run the [prepared usability study](phase10b_usability_study.md), including optional
keyboard/assistive-technology participants, before making broader usability claims.

## Reproduce

Start only the existing local synthetic staging service with approved test
credentials. Launch an isolated Edge/Chromium profile with localhost DevTools
access; never attach to a personal browser profile. Supply the pinned axe browser
script after checking its npm integrity. Then run:

```powershell
.\.venv\Scripts\python.exe -m scripts.qa_phase10b_accessibility --url http://127.0.0.1:8512 --endpoint http://127.0.0.1:9224 --output var/phase10b/accessibility-final-release
.\.venv\Scripts\python.exe -m scripts.qa_phase10b_accessibility --extras-only --url http://127.0.0.1:8512 --endpoint http://127.0.0.1:9224 --output var/phase10b/accessibility-final-release
```

Results, accessibility-tree summaries and screenshots remain ignored local QA
evidence under that output directory. No private screenshots are added to Git.
