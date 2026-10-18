"""Review and package an explicit public-source allowlist; never push or publish.

Pattern scanning is a release aid, not proof that all possible secrets are absent.
Original local reports, stores and screenshots are never deleted or rewritten.
"""

import argparse
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT_FILES = {"README.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md", "Dockerfile", "compose.yaml",
              "app.py", "config.py", "pyproject.toml", ".python-version", ".gitignore", ".dockerignore", ".env.example"}
PRIVATE_PARTS = {".git", ".venv", "var", "__pycache__", ".pytest_cache", ".pytest_tmp", ".ruff_cache", ".aws", ".codex", ".agents"}
REPORT_CSV = {"reports/phase5/" + name for name in ("anomaly_holdout.csv", "forecast_folds.csv", "forecast_predictions.csv")}
REPORT_CSV |= {"reports/phase6/" + name for name in ("calibration_labels.csv", "calibration_transactions.csv",
               "final_predictions.csv", "train_labels.csv", "train_transactions.csv")}
DEMO_SHA256 = "1d992cbd20c2b5265890db4dad4cb2420572788d2ccdbccfe3f7df4fe171f369"
PATTERNS = {
    "credential_prefix": re.compile(r"(?<![\w])(?:gh[pousr]_[A-Za-z0-9]{25,}|sk-[A-Za-z0-9]{24,}|AIza[\w-]{30,}|AKIA[0-9A-Z]{16})"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "absolute_windows_user_path": re.compile(r"(?i)[A-Z]:[\\/](?:Users|placement_personal)[\\/]"),
    "credential_assignment": re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*[\x22\x27][A-Za-z0-9_+/=-]{20,}[\x22\x27]"),
}


def candidates(root):
    root = root.resolve()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in PRIVATE_PARTS for part in relative.parts) or not path.is_file() or path.is_symlink():
            continue
        try:
            path.resolve().relative_to(root)
        except ValueError:
            continue
        name = relative.as_posix()
        if len(relative.parts) == 1:
            include = path.name in ROOT_FILES or path.name.startswith("requirements") and path.suffix == ".txt"
        elif relative.parts[0] in {"src", "api", "scripts", "tests"}:
            include = path.suffix == ".py"
        elif name == ".github/workflows/ci.yml" or name == ".streamlit/config.toml":
            include = True
        elif relative.parts[0] == "data":
            include = name == "data/synthetic_transactions.csv"
        elif relative.parts[0] == "docs":
            include = path.suffix in {".md", ".mmd", ".svg"} or name.startswith("docs/submission/assets/") and (
                path.suffix in {".png", ".json", ".mp4", ".srt"} or path.name == "synthetic-anomaly-benchmark.csv")
        elif relative.parts[0] == "reports":
            include = (path.suffix in {".md", ".json", ".html"} and "screenshots" not in relative.parts
                       and path.name not in {"release_manifest.json", "release_audit.json", "security_scan.json"}) or name in REPORT_CSV
        else:
            include = False
        if include:
            yield path


def inspect(root):
    files, findings = [], []
    for path in candidates(root):
        data = path.read_bytes()
        name = path.relative_to(root).as_posix()
        files.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        if path.suffix not in {".png", ".mp4"}:
            try:
                text = data.decode("utf-8-sig")
            except UnicodeError:
                findings.append({"path": name, "kind": "unreviewed_text_encoding"})
                continue
            for number, line in enumerate(text.splitlines(), 1):
                for kind, pattern in PATTERNS.items():
                    if pattern.search(line):
                        findings.append({"path": name, "line": number, "kind": kind})
        if name == "data/synthetic_transactions.csv" and hashlib.sha256(data).hexdigest() != DEMO_SHA256:
            findings.append({"path": name, "kind": "unrecognized_demo_data"})
    return {"files": files, "findings": findings, "pattern_scan_passed": not findings,
            "license_present": (root / "LICENSE").is_file(),
            "history": "No local Git history" if not (root / ".git").exists() else "Git history needs separate staged/history review",
            "limitations": ["Pattern matching cannot prove absence of every secret or personal datum.",
                            "Only new submission screenshots are packaged; historical screenshots/logs/databases/caches remain local.",
                            "Financial CSVs are limited to the approved demo and known synthetic benchmark outputs."]}


def package(root, destination, review):
    if review["findings"] or not review["license_present"]:
        raise ValueError("Resolve release findings and confirm a license before creating the source archive")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for item in review["files"]:
            path = root / item["path"]
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise ValueError("A file changed after review; rerun the release audit")
            info = zipfile.ZipInfo("CashGuard-AI/" + item["path"], date_time=(2026, 10, 18, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return {"file": destination.name, "bytes": destination.stat().st_size,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "members": len(review["files"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--archive", type=Path, default=Path("var/phase9/release/CashGuard-AI-source.zip"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = inspect(root)
    report["verified_at_utc"] = datetime.now(timezone.utc).isoformat()
    if args.build:
        report["archive"] = package(root, args.archive, report)
        (args.archive.parent / "git-paths.txt").write_text(
            "\n".join(item["path"] for item in report["files"]) + "\n", encoding="utf-8")
    output = root / "reports/phase9/release_manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "files"}, indent=2))
    if report["findings"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
