# Intended GitHub repository and publication procedure

Verified target: **https://github.com/MoAftab-01/CashGuard-AI**.
The connected account is `MoAftab-01`. Metadata shows admin/push permission, public
visibility, and an empty branch list. No remote code, commits, settings or visibility
were modified. The initial audit found no local Git history. At the owner's request,
release preparation now initializes local branch `main` and commits only the reviewed
release paths. This local preparation does not authorize a push.
Recheck the target immediately before any approved push; do not overwrite new work.

Owner confirmed **MIT** for application code. The root LICENSE implements that choice.
Gemma weights and dependencies retain their own terms; the release contains no weights.

Suggested About description:

> Local financial early-warning analytics for freelancers: cash-flow forecasts,
> explainable anomaly review, scenarios and grounded Gemma 3 insights.

Suggested topics, only if approved: `python`, `streamlit`, `fastapi`, `gemma`, `ollama`,
`cash-flow`, `financial-analytics`, `mlflow`, `local-first`.

## Reviewable source archive

Run `python -m scripts.prepare_release --build`. The archive is written to ignored
`var/phase9/release/CashGuard-AI-source.zip`; the file/hash manifest is recorded under
`reports/phase9/release_manifest.json`. This is a source distribution of the existing
project, not a replacement workspace. It excludes virtual environments, caches,
databases, weights, credentials, raw logs, arbitrary CSVs and historical screenshots.
New screenshot/video assets and known synthetic benchmark artifacts are included.
Original local artifacts remain intact. Inspect the manifest and archive before approval.

## Local commit preparation and approval boundary

The local preparation uses the existing workspace and the reviewed path list. The
configured Git author identity is retained; global Git configuration is not changed.
Disable automatic line-ending conversion locally so committed blobs retain the exact
reviewed bytes. Inspect staged names and hashes before committing:

```powershell
git init -b main
git config --local core.autocrlf false
git remote add origin https://github.com/MoAftab-01/CashGuard-AI.git
git ls-remote origin
# Stop and inspect if any remote branch now exists. Never force-push.
git add --pathspec-from-file=var/phase9/release/git-paths.txt
git diff --cached --stat
git diff --cached --name-only
# Inspect the staged files and run the release scan again.
git commit -m "Prepare CashGuard AI local analytics release"
```

Do not rerun initialization/remote creation if already prepared. Check `git status`,
`git remote -v`, `git log -1` and the local preparation receipt first.

`git-paths.txt` is generated from the reviewed release manifest. Configure a truthful
local Git author identity first if none exists. Do not invent an email, backdate the
commit or change global Git identity. These commands are instructions, not executed
publication. Do not run `git add .` on an unaudited workspace. The exact commit file
list and commit receipt are kept locally under ignored `var/phase9/release/`.

## Push only after separate explicit owner approval

After approval, recheck remote branches and run `git push -u origin main`. Stop if the
remote has changed; never force-push. No push is part of local commit preparation.

After pushing, verify the public README, code, LICENSE, synthetic dataset and assets
in a signed-out browser. Let the GitHub workflow actually run; add a status badge only
after checking its real result. Do not infer hosted success from local tests. Note any
post-deadline changes honestly. Record the submitted commit SHA for reproducibility.
