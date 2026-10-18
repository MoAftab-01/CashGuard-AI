# Phase 6 selection protocol (declared before new final-test generation)

The Phase 5 holdout has already been inspected and is diagnostic historical data.
It will not be described as an untouched test of the improvements. The new benchmark
has chronological training (2025-01-01, 120 days, seed 1729), calibration (next 60 days,
seed 2718) and final test (next 60 days, seed 31415). Generate the final partition only
after calibration selection is saved. No final-test results may alter this policy.

Each partition has daily variable groceries, transport, shopping and business receipts,
plus monthly salary, rent and subscription payments. Lognormal amount sigma is 0.3.
Zero transport entries every nineteenth day are valid background activity. Calibration
and final partitions inject an amount multiplier every fifth day, rotating categories
and multipliers 2/4/12, plus a 3x salary in the second salary month. A one-off insurance
expense is legitimate background. Ground-truth labels stay outside transaction features.
These labels describe injected amount changes only, never fraud or all unusualness.

Candidate families, fixed before final evaluation:

1. Existing six-feature Isolation Forest with its unchanged auto threshold.
2. Same frozen forest, threshold calibrated on background calibration scores.
3. Isolation Forest using robust category-relative amount deviation only.
4. Same amount forest with training-learned recurring-payment references.
5. Simple robust category amount deviation, no forest.
6. Same statistical baseline with recurring-payment references.

All forests use 200 trees and seed 42. Amount deviations use log1p absolute cents,
category/direction medians and 1.4826 * MAD, floored at 0.15 log units. Sparse groups
(fewer than three examples) use direction/global references. Recurring references
reuse existing schedule detection, require three historical occurrences, and match
the expected date within two days. Recurring payments are never exempted from amount
checks. Amount-only candidates deliberately do not detect weekday-only anomalies.

Calibrated thresholds are the 95th percentile (`method="higher"`) of background
calibration scores, strict greater-than alerts; statistical thresholds also have a
predeclared minimum robust deviation of 3.5. Calibration needs at least 30 background
records spanning at least 14 days. Select among candidates with calibration FPR <= 5%,
by greatest F1, then precision, recall, and simpler model (statistical/context first
on an exact tie). These are synthetic selection criteria, not a promised live FPR.
Freeze training features, model and threshold; do not refit before final scoring.
All six candidates then score exactly the same final examples; no post-test tuning.

Severity uses the frozen calibration score percentile as a rank, not a probability.
Unscored rows are not assigned a normal severity. Non-alerts are Informational;
alerts are Review recommended; an alert is High priority only if its background
calibration percentile is >= 99% and amount/reference >= 3. Recurring status provides
context and cannot downgrade a flagged large amount. No alerts are suppressed by UI.

The production dashboard will expose the calibrated option explicitly alongside the
legacy engine, retaining legacy APIs and reproducibility. Unlabeled live calibration
uses the recent past as a reference population without assuming confirmed normal
labels; its realized future false-positive rate is unknown. Sparse calibration stays
unscored with warnings. Forecast calculations and model weights remain unchanged.
