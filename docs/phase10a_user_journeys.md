# Phase 10A user journeys

## First visit

Open the local app or synthetic staging URL. Home has a single landing action:
Launch synthetic walkthrough. The sidebar also offers Start demo. Both explicitly
use fictional opening cash 2,500.00 and cash floor 500.00. These are sample assumptions,
not a connection to a bank. Your own CSV requires an explicit opening balance.

Home shows estimated cash, income, expenses and the 30-day estimate, followed by one
cash chart and two observations. Use Explore your forecast, Try a what-if plan or
Ask about your cash for the next task. Recent activity and net cash flow remain in
Recent activity and cash-flow detail.

## Explore spending and unusual activity

Select Explore. Transactions starts with search and a concise table; More filters
contains dates, categories and direction. Filters affect the table/export only.
Download filtered CSV retains spreadsheet-safe text and exact financial precision.
Spending breakdown contains monthly income/expenses and category spending for the
full imported history. Complete transaction fields retains normalized IDs/metadata.

Explore's Cash forecast view shows the same 30-day forecast and shortfalls. Change
Minimum cash threshold in Cash settings; the cash floor changes the breach test,
not the projected cash calculation. Analysis settings retains cutoff and irregular
income controls. Read assumptions before relying on any projection.

Unusual Activity starts with review status and search. More review filters retains
category, amount, severity and recurring-context filters. The table shows why an
item was flagged. Scores, timeline and review method, and the historical comparison
panel retain the technical investigation capabilities. Zero alerts does not establish
zero risk, and unscored transactions have not been assessed as normal.

Financial Risk retains cash buffer, expense/income ratio, shortfalls, ranked reasons,
and the heuristic component points/chart in How Financial Risk is calculated.

## Plan for a change

Select Plan and choose a labeled preset, or open Customize this plan. Results appear
before the custom form. Unexpected expense uses an illustrative 500 expense;
Reduced income uses 20%; Increased recurring costs uses 10% on all projected expense
events, including averaged spending. Delayed income chooses the first supported
recurring inflow and delays it seven days. It is unavailable without such an inflow.
Review the actual custom values and event before relying on the example.

Compare projected minimum cash, closing change, breach dates and the baseline/scenario
chart. Reset plan returns to the unchanged projection. An invalid amount blocks plan
results and reset recovers. Historical balances are never edited by a scenario.

## Ask for an explanation

AI Assistant offers four guided questions. A calculated answer is always available
from the existing analytics. If a permitted model is available, Generate AI Insights
requests and validates the original structured report. Switching questions reuses
that validated report; it does not make additional inference requests. Full explanations
and calculated evidence exposes every original section and supporting fact.

The visible status identifies local Ollama, configured hosted processing or deterministic
mode. Model settings are below the answer. Public staging deliberately uses deterministic
mode and cannot enable a provider just by changing a model name. Local setup remains
optional; no model is downloaded automatically. A missing/failed model leaves a clearly
labeled calculated answer rather than a fabricated AI response.

## Advanced and returning users

Advanced contains the complete native view directory, Model Evaluation and Data quality.
Local evaluations still require explicit button clicks; public evaluation remains fixed
synthetic evidence. Private MLflow and operational monitoring retain their existing
local instructions and authentication boundaries.

Existing internal route names and widget keys remain supported. View-only deep links
can open the forecast, plan, assistant or evaluation; unknown links do not supply financial
values. Transaction/review filters and scenario settings survive navigation. Replacing a
file clears affected financial/AI caches and old filters; verify your opening cash and
currency again. Clear session data releases results, resets routing and creates a fresh
session identifier. Real uploads remain disabled in public mode.
