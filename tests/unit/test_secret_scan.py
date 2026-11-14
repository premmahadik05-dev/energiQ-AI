"""The repository must not contain obvious secrets, and the scanner itself must be able to find them."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_secrets", ROOT / "scripts" / "check_secrets.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_repository_has_no_obvious_secrets():
    assert mod.scan() == []


def test_scanner_detects_known_patterns():
    rx = mod.PATTERNS
    assert rx["AWS access key id"].search("key = AKIAABCDEFGHIJKLMNOP")  # secret-scan: allow
    assert rx["private key block"].search("-----BEGIN RSA PRIVATE KEY-----")  # secret-scan: allow
    assert rx["GitHub token"].search("ghp_" + "a" * 36)  # secret-scan: allow
    assert rx["hard-coded password/secret assignment"].search('password = "hunter2hunter2"')  # secret-scan: allow
    assert not rx["AWS access key id"].search("AKIA-too-short")
