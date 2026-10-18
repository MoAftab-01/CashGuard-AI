# Contributing

Use Python 3.12 and the pinned developer lock. Run `python -m pip check`,
`python -m ruff check .`, `python -m compileall -q api src scripts app.py config.py`
and `python -m pytest -q` before proposing changes. The normal suite needs no running
Ollama or model download. MLflow tests run locally when the optional dependency exists.

Preserve exact integer-cent/Decimal calculations and chronological training boundaries.
Add meaningful regression coverage for financial behavior, leakage and privacy changes.
Keep UI code separate from calculations. Do not replace working algorithms to match
synthetic benchmark labels. A known holdout replay is not new independent validation.

Use fictional inputs in examples, screenshots and reports. Never submit private
transactions, credentials, local databases, model weights or raw browser/session logs.
Before a release, run `python -m scripts.prepare_release` and review the candidate file
manifest. New contributions must have the rights necessary for MIT distribution;
third-party libraries/models retain their own licenses and terms.

Keep post-deadline changes identified in release notes/README when preparing a contest
entry. Do not backdate commits or imply hosted CI passed before it actually ran.
