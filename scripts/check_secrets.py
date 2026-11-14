"""Minimal secret scanner for tracked files (a safety net, not a replacement for a dedicated tool such as gitleaks).

Exit status 1 if a likely secret is found. Test fixtures, documentation examples and the `.env.example` template are
allowed to contain obviously fake passwords; a line may also carry the marker ``secret-scan: allow``.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "AWS access key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private key block": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "API key (sk-...)": re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{32,}\b"),
    "hard-coded password/secret assignment": re.compile(r"""(?i)\b(?:password|passwd|secret_key|api_key|token)\s*[:=]\s*['"](?P<value>[^'"\s]{12,})['"]"""),
}
ALLOW_PATHS = ("tests/", "docs/", ".env.example", ".github/workflows/ci.yml", "frontend/src/test", "frontend/src/**/*.test.")
DOTTED_NAME = re.compile(r"[A-Za-z][\w-]*(?:\.[\w-]+)+")
SKIP_SUFFIXES = {".png", ".jpg", ".pdf", ".docx", ".pptx", ".gz", ".csv", ".json", ".lock"}


SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".venv", "venv", "dist", "artifacts", "data"}


def tracked_files() -> list[Path]:
    """Files that would be committed: ask git when this is a repository, otherwise walk the tree with the same exclusions as .gitignore
    (for example an unzipped release, which has no .git folder). Local `.env` files are ignored by git and so are not scanned either way."""
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, check=True)
        return [ROOT / p for p in out.stdout.decode().split("\0") if p]
    except (subprocess.CalledProcessError, FileNotFoundError):
        found = []
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                if name == ".env" or (name.startswith(".env.") and name != ".env.example") or name.endswith((".db", ".sqlite3", ".pyc")):
                    continue
                found.append(Path(dirpath) / name)
        return found


def scan() -> list[str]:
    findings = []
    for path in tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        if path.suffix.lower() in SKIP_SUFFIXES or "node_modules" in rel or not path.is_file():
            continue
        allowed_path = rel.startswith(ALLOW_PATHS[:3]) or rel in ALLOW_PATHS or ".test." in rel or rel.startswith("frontend/src/test")
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            if "secret-scan: allow" in line:
                continue
            for label, rx in PATTERNS.items():
                m = rx.search(line)
                if not m:
                    continue
                if label == "hard-coded password/secret assignment":
                    value = m.group("value")
                    if allowed_path or DOTTED_NAME.fullmatch(value):  # e.g. a storage key such as "energiq.token"
                        continue
                findings.append(f"{rel}:{n}: {label}")
    return findings


if __name__ == "__main__":
    hits = scan()
    for h in hits:
        print(h)
    print(f"{len(hits)} finding(s)")
    sys.exit(1 if hits else 0)
