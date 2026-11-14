"""Static checks of the deployment files. They do not build images (see docs/12_deployment.md for what has and has not been run).

They guard against the mistakes that cost a deployment its first start: a ``COPY`` of something that is not in the repository or is excluded by
``.dockerignore``, an ``ENERGIQ_*`` variable that the application silently ignores (``Settings`` has ``extra="ignore"``, so a typo is never reported),
and an entrypoint that does not seed or does overwrite the society artifacts.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from backend.app.config import Settings

REPO = Path(__file__).resolve().parents[2]
DOCKERFILES = [REPO / "docker" / "backend.Dockerfile", REPO / "docker" / "frontend.Dockerfile"]
FIELDS = {"ENERGIQ_" + name.upper() for name in Settings.model_fields}


def _copy_sources(dockerfile: Path) -> list[str]:
    out = []
    for line in dockerfile.read_text().splitlines():
        parts = line.split()
        if parts and parts[0] == "COPY" and not any(p.startswith("--from=") for p in parts):
            args = [p for p in parts[1:] if not p.startswith("--")]
            out += args[:-1]  # the last argument is the destination
    return out


def _ignored(path: str, patterns: list[str]) -> bool:
    """Prefix rule of .dockerignore as far as this repository uses it: a pattern names a path or one of its parent folders."""
    rel = path.strip("./").rstrip("/")
    for pat in patterns:
        if pat.startswith("!") or "*" in pat:
            continue
        p = pat.strip("/")
        if rel == p or rel.startswith(p + "/"):
            return True
    return False


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=lambda p: p.name)
def test_every_copy_source_exists_and_is_not_excluded_by_dockerignore(dockerfile):
    patterns = [ln.strip() for ln in (REPO / ".dockerignore").read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    sources = _copy_sources(dockerfile)
    assert sources, "no COPY lines parsed"
    for src in sources:
        assert (REPO / src).exists(), f"{dockerfile.name}: COPY {src} does not exist in the repository"
        assert not _ignored(src, patterns), f"{dockerfile.name}: COPY {src} is excluded by .dockerignore, so the build would fail"


def test_the_api_image_ships_the_society_data_and_points_the_application_at_it():
    text = (REPO / "docker" / "backend.Dockerfile").read_text()
    sources = _copy_sources(REPO / "docker" / "backend.Dockerfile")
    assert "data/society/processed" in sources and "artifacts/society" in sources, "without these the admin 'import bundled communities' action answers 404"
    env = dict(re.findall(r"^\s*(?:ENV\s+)?([A-Z_]+)=(\S+?)(?:\s*\\)?$", text, re.M))
    assert env["ENERGIQ_SOCIETY_DATA_DIR"] == "/app/data/society/processed"
    assert env["ENERGIQ_SOCIETY_DIR"].startswith("/data/"), "society artifacts are written (uploaded societies are trained there), so they live on the /data volume"
    assert env["SOCIETY_SEED_DIR"] == "/app/artifacts/society"
    assert "/data/society" in text.split("mkdir -p", 1)[1].split("&&", 1)[0]


@pytest.mark.parametrize("path", ["docker/backend.Dockerfile", "docker-compose.yml", "infrastructure/aws/energiq-stack.yaml", ".env.example"])
def test_every_energiq_variable_in_the_deployment_files_is_a_real_setting(path):
    names = set(re.findall(r"\bENERGIQ_[A-Z0-9_]+\b", (REPO / path).read_text()))
    assert names, path
    unknown = sorted(names - FIELDS)
    assert not unknown, f"{path} sets variables the application ignores: {unknown}"


def _run_entrypoint(tmp: Path, seed: Path, target: Path):
    env = {"PATH": os.environ["PATH"], "SOCIETY_SEED_DIR": str(seed), "ENERGIQ_SOCIETY_DIR": str(target), "ENERGIQ_SKIP_MIGRATIONS": "1"}
    return subprocess.run(["sh", str(REPO / "docker" / "backend-entrypoint.sh"), "echo", "started"], env=env, cwd=tmp, capture_output=True, text=True, timeout=60)


def test_entrypoint_seeds_the_society_volume_once_and_never_overwrites_it(tmp_path):
    seed, target = tmp_path / "seed", tmp_path / "data" / "society"
    (seed / "fox" / "models").mkdir(parents=True)
    (seed / "fox" / "evaluation.json").write_text('{"v": 1}')
    (seed / "fox" / "models" / "m.bin").write_bytes(b"model")

    r = _run_entrypoint(tmp_path, seed, target)
    assert r.returncode == 0 and r.stdout.strip().endswith("started"), r.stderr
    assert (target / "fox" / "evaluation.json").read_text() == '{"v": 1}' and (target / "fox" / "models" / "m.bin").read_bytes() == b"model"
    assert (target / ".seeded").is_file()

    # the application writes into the volume (a trained, uploaded society) and the image is later updated with different seed files
    (target / "fox" / "evaluation.json").write_text('{"v": "changed by the application"}')
    (target / "mine").mkdir()
    (target / "mine" / "evaluation.json").write_text("{}")
    (seed / "fox" / "evaluation.json").write_text('{"v": 2}')
    r2 = _run_entrypoint(tmp_path, seed, target)
    assert r2.returncode == 0 and "copying" not in r2.stdout
    assert (target / "fox" / "evaluation.json").read_text() == '{"v": "changed by the application"}'
    assert (target / "mine" / "evaluation.json").is_file()


def test_an_interrupted_first_copy_is_repeated_because_the_marker_is_written_last(tmp_path):
    seed, target = tmp_path / "seed", tmp_path / "data" / "society"
    (seed / "bull").mkdir(parents=True)
    (seed / "bull" / "evaluation.json").write_text("{}")
    target.mkdir(parents=True)  # a directory left behind by an earlier, interrupted start: no marker
    r = _run_entrypoint(tmp_path, seed, target)
    assert r.returncode == 0 and (target / "bull" / "evaluation.json").is_file() and (target / ".seeded").is_file()


def test_entrypoint_without_a_seed_directory_does_not_fail(tmp_path):
    r = _run_entrypoint(tmp_path, tmp_path / "does-not-exist", tmp_path / "t")
    assert r.returncode == 0 and not (tmp_path / "t").exists()
