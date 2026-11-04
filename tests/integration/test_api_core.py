"""Auth, upload, ownership and role checks against the real API."""
from __future__ import annotations

import time

import jwt
import pytest
from conftest import PASSWORD, login, make_settings, signup, synthetic_csv, upload
from fastapi.testclient import TestClient

from backend.app.main import create_app

API = "/api/v1"


def test_health_and_metrics(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    r = client.get("/health/ready")
    assert r.status_code == 200 and r.json()["database"] == "up"
    client.get(f"{API}/datasets")  # 401, still counted
    text = client.get("/metrics").text
    assert 'energiq_http_requests_total{method="GET",route="/api/v1/datasets",status="401"} 1' in text
    assert "energiq_http_request_duration_seconds_count" in text


def test_register_login_me_and_validation(client):
    bad = [("not-an-email", PASSWORD), ("a@b.co", "short1"), ("a@b.co", "onlyletterspassword"), ("a@b.co", "password1234")]
    for email, pw in bad:
        assert client.post(f"{API}/auth/register", json={"email": email, "password": pw}).status_code == 422
    h = signup(client, "Alice@Example.com")
    assert client.post(f"{API}/auth/register", json={"email": "alice@example.com", "password": PASSWORD}).status_code == 409
    me = client.get(f"{API}/auth/me", headers=h).json()
    assert me["email"] == "alice@example.com" and me["role"] == "analyst" and "password" not in str(me)
    assert client.post(f"{API}/auth/login", json={"email": "alice@example.com", "password": "wrong-Password-1"}).status_code == 401
    unknown = client.post(f"{API}/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    wrong = client.post(f"{API}/auth/login", json={"email": "alice@example.com", "password": "wrong-Password-1"})
    assert unknown.status_code == wrong.status_code == 401 and unknown.json() == wrong.json()  # no user enumeration


def test_tokens_are_validated(client, app):
    h = signup(client, "bob@example.com")
    assert client.get(f"{API}/auth/me").status_code == 401
    assert client.get(f"{API}/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    key = app.state.settings.secret_key
    now = int(time.time())
    expired = jwt.encode({"sub": "1", "exp": now - 10}, key, algorithm="HS256")
    wrong_key = jwt.encode({"sub": "1", "exp": now + 600}, "another-secret-" + "y" * 40, algorithm="HS256")
    none_alg = jwt.encode({"sub": "1", "exp": now + 600}, key=None, algorithm="none")
    no_exp = jwt.encode({"sub": "1"}, key, algorithm="HS256")
    for tok in (expired, wrong_key, none_alg, no_exp):
        assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401
    assert client.get(f"{API}/auth/me", headers=h).status_code == 200


def test_login_rate_limit(client):
    signup(client, "carol@example.com")  # its successful login counts as the 1st of 5 allowed attempts per 5 minutes
    codes = [client.post(f"{API}/auth/login", json={"email": "carol@example.com", "password": "bad-Password-9"}).status_code for _ in range(6)]
    assert codes[:4] == [401] * 4 and codes[4:] == [429, 429]
    r = client.post(f"{API}/auth/login", json={"email": "carol@example.com", "password": "bad-Password-9"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1


def test_registration_can_be_disabled(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, allow_registration=False))) as c:
        assert c.post(f"{API}/auth/register", json={"email": "x@example.com", "password": PASSWORD}).status_code == 403
        assert c.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": "AdminPass-12345"}).status_code == 200


def test_prod_refuses_default_secret(tmp_path):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(make_settings(tmp_path, env="prod", secret_key="dev-only-insecure-secret-change-me-0123456789abcdef"))
    with pytest.raises(RuntimeError, match="CORS"):
        create_app(make_settings(tmp_path, env="prod", cors_origins=["*"]))


def test_upload_flow_and_report(client):
    h = signup(client, "dave@example.com")
    r = upload(client, h, synthetic_csv(days=60))
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["job"]["kind"] == "ingest"
    job = client.get(f"{API}/jobs/{body['job']['id']}", headers=h).json()
    assert job["status"] == "succeeded" and job["result"]["suitable_for_forecasting"] is True
    ds = client.get(f"{API}/datasets/{body['dataset']['id']}", headers=h).json()
    assert ds["status"] == "ready" and ds["hours"] == 24 * 60 and 0.9 * 24 * 60 < ds["valid_hours"] <= 24 * 60
    assert ds["quality_score"] > 90 and ds["report"]["rows_read"] == 24 * 60 and ds["report"]["unit_declared"] == "kW"
    assert client.get(f"{API}/datasets", headers=h).json()[0]["id"] == ds["id"]
    rd = client.get(f"{API}/datasets/{ds['id']}/readings?resolution=daily&limit=10", headers=h).json()
    assert rd["resolution"] == "daily" and len(rd["points"]) == 10 and rd["points"][0]["valid_hours"] <= 24
    hp = client.get(f"{API}/datasets/{ds['id']}/profile", headers=h).json()
    assert len(hp["hourly_profile"]) == 24
    ev = max(hp["hourly_profile"], key=lambda p: p["mean_kw"])["hour"]
    assert ev in (18, 19, 20)  # the synthetic evening peak is recovered from the stored data


def test_upload_rejections(client, tmp_path):
    h = signup(client, "erin@example.com")
    good = synthetic_csv(days=40)
    assert upload(client, h, good, filename="meter.exe").status_code == 415
    assert upload(client, h, "a,b\n\x00\x01\x02", filename="x.csv").status_code == 415
    assert upload(client, h, "", filename="x.csv").status_code == 422
    assert upload(client, h, "x" * (6 * 1024 * 1024), filename="big.csv").status_code == 413
    assert upload(client, h, good, unit="furlongs").status_code == 422
    assert upload(client, h, good, timestamp_column="").status_code == 422
    assert upload(client, h, good, delimiter="abc").status_code == 422
    r = upload(client, h, good, value_column="does_not_exist")
    assert r.status_code == 202
    job = client.get(f"{API}/jobs/{r.json()['job']['id']}", headers=h).json()
    assert job["status"] == "failed" and "Missing expected column" in job["error"]
    assert client.get(f"{API}/datasets/{r.json()['dataset']['id']}", headers=h).json()["status"] == "failed"
    daily = synthetic_csv(days=5).replace(":00:00", ":00:00")  # hourly is fine; now make it coarser than hourly
    coarse = "time,kw\n" + "\n".join(f"2022-01-{d:02d} 00:00:00,1.0" for d in range(1, 29))
    r2 = upload(client, h, coarse)
    assert client.get(f"{API}/jobs/{r2.json()['job']['id']}", headers=h).json()["error"].startswith("Sampling interval")
    short = upload(client, h, synthetic_csv(days=5))
    assert client.get(f"{API}/datasets/{short.json()['dataset']['id']}", headers=h).json()["report"]["suitable_for_forecasting"] is False
    assert client.post(f"{API}/datasets/{short.json()['dataset']['id']}/train", headers=h).status_code == 422
    assert daily


def test_filename_is_sanitised_and_never_used_as_a_path(client, app):
    h = signup(client, "frank@example.com")
    r = upload(client, h, synthetic_csv(days=30), filename="../../etc/passwd.csv")
    assert r.status_code == 202 and r.json()["dataset"]["original_filename"] == "passwd.csv"
    uploads = list(app.state.settings.upload_dir.rglob("*.csv"))
    assert all(p.name.startswith("dataset_") for p in uploads)


def test_ownership_isolation_and_roles(client, app):
    a, b = signup(client, "owner@example.com"), signup(client, "other@example.com")
    ds = upload(client, a, synthetic_csv(days=40)).json()
    did, jid = ds["dataset"]["id"], ds["job"]["id"]
    for method, url in (("get", f"/datasets/{did}"), ("delete", f"/datasets/{did}"), ("get", f"/datasets/{did}/readings"),
                        ("get", f"/jobs/{jid}"), ("post", f"/datasets/{did}/train"), ("get", f"/anomalies?dataset_id={did}")):
        assert getattr(client, method)(API + url, headers=b).status_code == 404, url
    assert client.get(f"{API}/datasets", headers=b).json() == []
    assert client.post(f"{API}/forecasts", headers=b, json={"dataset_id": did}).status_code == 404
    # roles: admin endpoints are admin-only; viewers cannot mutate
    assert client.get(f"{API}/admin/users", headers=a).status_code == 403
    admin = login(client, "admin@example.com", "AdminPass-12345")
    users = client.get(f"{API}/admin/users", headers=admin).json()
    viewer = next(u for u in users if u["email"] == "other@example.com")
    assert client.patch(f"{API}/admin/users/{viewer['id']}", headers=admin, json={"role": "viewer"}).json()["role"] == "viewer"
    assert upload(client, b, synthetic_csv(days=30)).status_code == 403
    assert client.get(f"{API}/datasets", headers=b).status_code == 200
    me = client.get(f"{API}/auth/me", headers=admin).json()
    assert client.patch(f"{API}/admin/users/{me['id']}", headers=admin, json={"role": "viewer"}).status_code == 400
    # deactivation takes effect immediately for already-issued tokens
    assert client.patch(f"{API}/admin/users/{viewer['id']}", headers=admin, json={"is_active": False}).status_code == 200
    assert client.get(f"{API}/datasets", headers=b).status_code == 401
    actions = [e["action"] for e in client.get(f"{API}/admin/audit?limit=200", headers=admin).json()]
    assert {"register", "login", "dataset_upload", "admin_user_change"} <= set(actions)
