# Offline model monitoring

Origin: synthetic

Local aggregate report; no raw descriptions, account IDs or transaction rows.
Distribution shifts request review; they do not prove model failure or trigger retraining.

Defaults: 100 transactions spanning 30 days per window; 50 scored rows for alert rates.
KS distance >= 0.20; category JS divergence >= 0.10 bits; ratio delta >= 0.20; alert-rate delta >= 0.10.

## Background

Status: review_required

Rows: 492 reference / 234 current.

| Signal | Sufficient | Effect | Threshold | Review flag |
|---|---|---|---|---|
| absolute_amount_distribution | True | 0.039660204294350576 | 0.2 | False |
| category_distribution | True | 0.0021570305050482358 | 0.1 | False |
| expense_to_income_ratio | True | 0.3094206209372759 | 0.2 | True |
| alert_rate | False | None | 0.1 | None |

Drift is not proof of model failure and does not trigger retraining.
Fixed effect thresholds are review heuristics, not significance or false-positive guarantees.
Seasonality, payday timing, correlated transactions and window composition can change these diagnostics.
Missing alert flags remain unassessed. Compare identical engine/calibration policies.

## Deliberate Shift

Status: review_required

Rows: 492 reference / 234 current.

| Signal | Sufficient | Effect | Threshold | Review flag |
|---|---|---|---|---|
| absolute_amount_distribution | True | 0.5599854075463832 | 0.2 | True |
| category_distribution | True | 0.7045360211801448 | 0.1 | True |
| expense_to_income_ratio | True | 7.4855808222088225 | 0.2 | True |
| alert_rate | False | None | 0.1 | None |

Drift is not proof of model failure and does not trigger retraining.
Fixed effect thresholds are review heuristics, not significance or false-positive guarantees.
Seasonality, payday timing, correlated transactions and window composition can change these diagnostics.
Missing alert flags remain unassessed. Compare identical engine/calibration policies.

Not assessed: this command has no realized forecast outcome ledger.
Not assessed: no comparable scored-alert vectors supplied.

Reports contain aggregate financial evidence and fingerprints; keep user-supplied reports private.