"""The running API against the independent raw-data verifier.

All seven bundled communities are imported into a temporary database through the same function the admin endpoint uses. The verifier
(scripts/verify_society_raw_data.py, which imports nothing from this project) then re-computes every community from the RAW BDG2 readings and compares:
overview totals, every calendar month and every building, as served by the API, with its own numbers. Further tests change what the API returns and
require the comparison to fail, so that a passing comparison means something.

Needs data/society/raw_subset and data/society/processed (shipped) and artifacts/society (shipped; only the evaluation files are used).
"""
from __future__ import annotations

import importlib.util
import sys

import pytest
from fastapi.testclient import TestClient
from itest_support import REPO, login, make_settings, signup

from backend.app.main import create_app
from backend.app.services.society_import import import_processed

SCRIPT = REPO / "scripts" / "verify_society_raw_data.py"
SUBSET = REPO / "data" / "society" / "raw_subset"
FULL = REPO / "data" / "society" / "raw" / "bdg2"
PROCESSED = REPO / "data" / "society" / "processed"
ARTIFACTS = REPO / "artifacts" / "society"
KEYS = ["bull", "eagle", "fox", "hog", "peacock", "rat", "robin"]

pytestmark = pytest.mark.skipif(not (SUBSET / "subset_manifest.json").is_file() or not (PROCESSED / "societies.json").is_file(),
                                reason="raw subset or processed society data not present")

_spec = importlib.util.spec_from_file_location("verify_society_raw_data", SCRIPT)
V = importlib.util.module_from_spec(_spec)
sys.modules["verify_society_raw_data"] = V
_spec.loader.exec_module(V)


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("raw_vs_api")
    st = make_settings(tmp, society_dir=ARTIFACTS, society_data_dir=PROCESSED)
    app = create_app(st)
    with TestClient(app) as c:
        with app.state.db.session() as s:
            for key in KEYS:
                import_processed(s, key, st.society_data_dir, st.society_dir, log_fn=lambda *a: None)
        yield {"c": c, "admin": login(c, "admin@example.com", "AdminPass-12345"), "analyst": signup(c, "analyst@example.com")}


def _getter(env, who="admin"):
    def get(path, params=None):
        r = env["c"].get(path, headers=env[who], params=params)
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
        return r.json()
    return get


def _run(get, only=None):
    return V.run_verification(FULL, SUBSET, PROCESSED, api_get=get, only=only, force_subset=True)


def _failed(rep):
    return {c["id"] for c in rep["checks"] if not c["passed"]}


def test_api_reproduces_the_independent_raw_computation_for_every_community(env):
    rep = _run(_getter(env))
    assert _failed(rep) == set(), [c for c in rep["checks"] if not c["passed"]]
    api_checks = [c for c in rep["checks"] if ".api." in c["id"]]
    assert len(api_checks) == 3 * len(KEYS), "totals, monthly and buildings for each of the seven communities"
    assert sorted(rep["api"]) == KEYS
    for key, d in rep["api"].items():
        assert d["api_valid_hours"] == d["independent_valid_hours"] == rep["societies"][key]["missing"]["valid_hours"], key
        assert d["months_compared"] == 24 and d["buildings_compared"] == rep["societies"][key]["buildings"], key
        # the stored values have 3 decimals, so the API sum may differ from the sum of the raw readings by rounding only
        assert abs(d["api_energy_kwh"] - d["independent_energy_kwh"]) < 0.0005 * (d["buildings_compared"] + 1) * d["independent_valid_hours"], key


def test_a_wrong_energy_total_in_the_api_is_detected(env):
    """The allowed difference is the worst case of the 3-decimal storage: 0.0005 x (meters + 1) kWh per valid hour, about 105 kWh for Fox's 26.5 million kWh.
    An error of 500 kWh is far outside it; one of 25 kWh would (correctly) pass, which is why the report prints the tolerance next to every difference."""
    get = _getter(env)

    def shifted(delta):
        def wrong(path, params=None):
            data = get(path, params)
            if path.endswith("/overview"):
                data["totals"]["energy_kwh"] += delta
            return data
        return wrong
    assert "fox.api.totals" in _failed(_run(shifted(500.0), only=["fox"]))
    assert "fox.api.totals" not in _failed(_run(shifted(25.0), only=["fox"])), "a difference inside the documented rounding tolerance must not be reported as an error"


def test_a_missing_month_in_the_api_is_detected(env):
    get = _getter(env)

    def wrong(path, params=None):
        data = get(path, params)
        if path.endswith("/consumption"):
            data["points"] = data["points"][:-1]
        return data
    assert "fox.api.monthly" in _failed(_run(wrong, only=["fox"]))


def test_a_wrong_building_figure_in_the_api_is_detected(env):
    get = _getter(env)

    def wrong(path, params=None):
        data = get(path, params)
        if path.endswith("/buildings"):
            data["buildings"][0]["energy_kwh"] += 10.0
        return data
    assert "fox.api.buildings" in _failed(_run(wrong, only=["fox"]))


def test_without_an_admin_account_the_building_comparison_cannot_run_and_says_so(env):
    rep = _run(_getter(env, "analyst"), only=["fox"])
    bad = [c for c in rep["checks"] if not c["passed"]]
    assert [c["id"] for c in bad] == ["fox.api.buildings"] and "admin" in bad[0]["detail"], "the BDG2 identifiers are admin-only, so the check must fail loudly, not pass silently"


def test_a_society_that_was_not_imported_is_reported(env):
    get = _getter(env)

    def hide_fox(path, params=None):
        data = get(path, params)
        return [s for s in data if s["key"] != "fox"] if path == "/api/v1/societies" else data
    assert "fox.api.present" in _failed(_run(hide_fox, only=["fox"]))
