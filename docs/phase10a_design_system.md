# Phase 10A design system

The existing native Streamlit and Plotly interface is retained. No frontend framework,
paid dependency, new financial calculation or hosted model has been added.

## Task hierarchy

| Primary area | Views and retained capabilities |
|---|---|
| Home | Estimated balance, historical income/expenses, conditional 30-day balance, one history/forecast chart, outlook/risk observations, recent activity and net flow in details |
| Explore | Transactions and safe CSV export, spending breakdowns, Cash forecast, Unusual Activity, Financial Risk |
| Plan | Original scenario engine, four explicit hypothetical presets, reset, exact custom settings, baseline comparison and shortfall dates |
| AI Assistant | Guided questions, calculated summaries, optional grounded local/API provider output, full validated evidence and provider settings |
| Advanced | Model Evaluation, Data quality, complete view directory; private MLflow and monitoring retain their documented local startup paths |

`src/ui/navigation.py` owns labels, area membership and safe view slugs. Original
route IDs and the native `navigation` widget remain in the Advanced directory, so
existing integrations and tests retain a stable route contract. Explore has contextual
view pills; Home has direct next-action buttons. URL examples: `?view=home`,
`?view=forecast`, `?view=plan`, `?view=assistant`, `?view=evaluation`.
Known original page names also resolve. Financial data/settings never enter URLs.

## Visual foundations

| Token / pattern | Choice |
|---|---|
| Light surface / text | `#F8FAFC` / `#10213A` |
| Dark surface / text | `#0B1220` / `#E2E8F0` |
| Primary action | `#0F766E` with white text in both themes; sidebar active actions use the same readable pair |
| Dark supporting accent | Existing `#2DD4BF` for theme accents; primary button foreground/background are explicit |
| Focus | 3 px outline with 3 px offset; darker teal in light environments, light teal in dark environments |
| Typography | Native sans serif, moderate heading scale, tabular financial digits, wrapped metric values |
| Layout | 1,280 px maximum content width, compact header/context, native responsive columns and wrapped pills |
| Cards | Subtle neutral tint, low-contrast border and modest corner radius; no heavy shadow or gradient |
| Charts | Existing Plotly functions, transparent theme-aware surfaces, units, named traces and distinct line styles |
| Tables | Useful columns first; full fields, model scores and methodology remain in details |
| AI messages | Native chat containers with neutral material icons, short excerpt, distinct calculated/model labels |

Reusable styling/components live in `src/ui/components.py`; theme values remain in
`.streamlit/config.toml`. CSS targets native test IDs/semantic elements, not generated
Emotion class names. It never receives user transaction text. Browser QA checks
sampled computed contrast and chart boundaries; this is not a full WCAG certification.

## Progressive disclosure and trust

One visible data-basis line identifies the sample/private history, currency, cutoff
and estimated balances. Source counts, backend boundary and opening-cash assumptions
are in Data and assumptions. Cash settings, analysis settings and review methods
remain available in the sidebar. No opening balance is silently supplied for uploads.

Import errors and duplicate decisions continue to block analytics visibly. Forecast
breaches, provisional risk, warmup/unassessed activity and provider unavailability
remain explicit. Detailed assumptions and methodology use native expanders. The
public demo still blocks real uploads and shows read-only synthetic evaluation.

Question selection changes only the displayed section of existing verified outputs;
it never changes prompts, triggers inference or invents an open-ended conversation.
The selected question is shown as a UI selection, not fabricated chat history.
Only Generate AI Insights requests model output. Concise model excerpts preserve
the complete validated explanation and evidence in a clearly labeled expander;
these are explanations, not hidden chain-of-thought. Provider errors retain the
calculated summaries and never expose rejected output.

Preset amounts/percentages are labeled examples, not inferred financial facts:
500 emergency expense, seven-day delay of the first supported recurring inflow,
20% lower projected income, and 10% higher projected expenses. The cost preset
explicitly applies to all baseline projected expenses, including averaged spending.
Unavailable recurring inflows disable the delay preset. Presets replace rather than
silently combine settings. Custom controls and the underlying scenario engine are
unchanged; reset restores the zero-change baseline and invalidates stale AI context.
