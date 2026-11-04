"""Security behaviour: authentication coverage, IDOR, injection, XSS, headers, CORS, limits, error hygiene."""
from __future__ import annotations

from conftest import PASSWORD, login, make_settings, signup, synthetic_csv, upload
from fastapi.testclient import TestClient

from backend.app.main import create_app

API = "/api/v1"
PUBLIC = {("POST", "/api/v1/auth/register"), ("POST", "/api/v1/auth/login")}


def test_every_api_route_requires_authentication(app):
    client = TestClient(app)
    spec = app.openapi()
    checked = 0
    for path, methods in spec["paths"].items():
        if not path.startswith("/api/v1"):
            continue
        for method in methods:
            if (method.upper(), path) in PUBLIC:
                continue
            url = path.replace("{dataset_id}", "1").replace("{job_id}", "1").replace("{model_id}", "x").replace(
                "{forecast_id}", "1").replace("{anomaly_id}", "1").replace("{tariff_id}", "1").replace("{user_id}", "1").replace(
                "{nid}", "1").replace("{group}", "evaluation").replace("{name}", "fig_a.png")
            assert "{" not in url, url
            r = client.request(method.upper(), url)
            assert r.status_code == 401, f"{method.upper()} {path} -> {r.status_code}"
            checked += 1
    assert checked >= 40


def test_security_headers_and_cors(client):
    r = client.get("/health/live", headers={"Origin": "http://localhost:5173"})
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    evil = client.get("/health/live", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in evil.headers
    api = client.get(f"{API}/datasets")
    assert api.headers["cache-control"] == "no-store" and "default-src 'none'" in api.headers["content-security-policy"]
    pre = client.options(f"{API}/datasets", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in pre.headers
    assert api.headers["x-request-id"]


def test_mass_assignment_cannot_set_role(client):
    r = client.post(f"{API}/auth/register", json={"email": "m@example.com", "password": PASSWORD, "role": "admin", "is_active": True})
    assert r.status_code == 201 and r.json()["role"] == "analyst"


def test_injection_strings_are_data_not_code(client):
    h = signup(client, "inj@example.com")
    payload = "x'; DROP TABLE datasets; --"
    r = upload(client, h, synthetic_csv(days=30), name=payload)
    assert r.status_code == 202 and r.json()["dataset"]["name"] == payload
    assert client.get(f"{API}/datasets", headers=h).json()[0]["name"] == payload  # table still exists
    did = r.json()["dataset"]["id"]
    assert client.get(f"{API}/anomalies?dataset_id={did}&severity=high' OR '1'='1", headers=h).status_code == 422
    assert client.get(f"{API}/datasets/1%20OR%201=1", headers=h).status_code == 422
    assert client.get(f"{API}/datasets/{did}/readings?start=2020-01-01'--", headers=h).status_code == 422
    admin = login(client, "admin@example.com", "AdminPass-12345")
    assert client.get(f"{API}/admin/audit?action=' OR 1=1 --", headers=admin).json() == []


def test_report_escapes_user_text(client):
    h = signup(client, "xss@example.com")
    name = "<script>alert(1)</script><img src=x onerror=alert(2)>"
    did = upload(client, h, synthetic_csv(days=40), name=name).json()["dataset"]["id"]
    r = client.get(f"{API}/datasets/{did}/report", headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "<script>alert(1)</script>" not in r.text and "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text and "<img src=x" not in r.text
    assert "script-src" not in r.headers["content-security-policy"] and "default-src 'none'" in r.headers["content-security-policy"]


def test_idor_on_tariffs_notifications_and_anomalies(client):
    a, b = signup(client, "ia@example.com"), signup(client, "ib@example.com")
    t = client.post(f"{API}/tariffs", headers=a, json={"name": "mine", "currency": "EUR", "weekday_rates": [0.2] * 24,
                                                       "weekend_rates": [0.2] * 24}).json()
    assert client.delete(f"{API}/tariffs/{t['id']}", headers=b).status_code == 404
    assert [x["id"] for x in client.get(f"{API}/tariffs", headers=b).json()] == ["demo"]
    did = upload(client, a, synthetic_csv(days=40)).json()["dataset"]["id"]
    assert client.post(f"{API}/optimize/cost", headers=b, json={"dataset_id": did, "tariff_id": t["id"]}).status_code == 404
    assert client.get(f"{API}/datasets/{did}/report", headers=b).status_code == 404
    assert client.patch(f"{API}/anomalies/1", headers=b, json={"acknowledged": True}).status_code == 404
    assert client.post(f"{API}/notifications/1/read", headers=b).status_code == 404
    assert client.get(f"{API}/forecasts/1", headers=b).status_code == 404 and client.get(f"{API}/models/x", headers=b).status_code == 404


def test_upload_rate_limit(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, upload_per_hour=3))) as c:
        h = signup(c, "rl@example.com")
        codes = [upload(c, h, synthetic_csv(days=30)).status_code for _ in range(5)]
        assert codes == [202, 202, 202, 429, 429]


def test_register_rate_limit(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, register_per_hour=2))) as c:
        codes = [c.post(f"{API}/auth/register", json={"email": f"r{i}@example.com", "password": PASSWORD}).status_code for i in range(4)]
        assert codes == [201, 201, 429, 429]


def test_internal_errors_do_not_leak_details(app, monkeypatch):
    from backend.app.api import datasets as ds_api

    h = signup(TestClient(app), "err@example.com")
    c = TestClient(app, raise_server_exceptions=False)
    did = upload(c, h, synthetic_csv(days=30)).json()["dataset"]["id"]

    def boom(*a, **k):
        raise RuntimeError("secret internal detail /srv/db password=hunter2")

    monkeypatch.setattr(ds_api.data_svc, "load_series", boom)
    r = c.get(f"{API}/datasets/{did}/readings", headers=h)
    assert r.status_code == 500 and "hunter2" not in r.text and "secret" not in r.text and r.json()["request_id"]


def test_job_errors_hide_internal_exceptions(app, monkeypatch):
    from backend.app.services import data as data_svc

    c = TestClient(app)
    h = signup(c, "joberr@example.com")

    def boom(*a, **k):
        raise RuntimeError("connection string postgres://user:pw@host/db")

    monkeypatch.setattr(data_svc, "ingest_csv", boom)
    r = upload(c, h, synthetic_csv(days=30))
    job = c.get(f"{API}/jobs/{r.json()['job']['id']}", headers=h).json()
    assert job["status"] == "failed" and "postgres" not in str(job) and job["error"] == "Internal error; see server logs"


def test_password_hashes_never_leave_the_server(client):
    signup(client, "ph@example.com")
    admin = login(client, "admin@example.com", "AdminPass-12345")
    body = client.get(f"{API}/admin/users", headers=admin).text
    assert "password" not in body.lower() and "argon2" not in body.lower()


def test_token_in_query_string_is_not_accepted(client):
    h = signup(client, "q@example.com")
    token = h["Authorization"].split()[1]
    assert client.get(f"{API}/auth/me?access_token={token}").status_code == 401


def _login_status(c, ip_header: str | None):
    headers = {"X-Forwarded-For": ip_header} if ip_header else {}
    return c.post(f"{API}/auth/login", json={"email": "nobody@example.com", "password": "wrong-password-1"}, headers=headers).status_code


def test_forged_forwarded_for_cannot_dodge_login_rate_limit(tmp_path):
    """Behind one trusted proxy the client is the RIGHT-most X-Forwarded-For entry; entries to its left are attacker-chosen."""
    with TestClient(create_app(make_settings(tmp_path, trust_proxy=True, login_per_minute=3))) as c:
        codes = [_login_status(c, f"10.0.0.{i}, 203.0.113.7") for i in range(5)]  # different forged left entries, same real client
        assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]
        assert _login_status(c, "203.0.113.8") == 401  # a different real client is unaffected


def test_forwarded_for_is_ignored_unless_proxy_is_trusted(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, trust_proxy=False, login_per_minute=3))) as c:
        codes = [_login_status(c, f"198.51.100.{i}") for i in range(5)]  # varying the header must not help
        assert codes == [401, 401, 401, 429, 429]


def test_client_ip_hops_unit():
    from starlette.requests import Request

    from backend.app.security import client_ip

    def req(xff: str | None) -> Request:
        hdrs = [(b"x-forwarded-for", xff.encode())] if xff else []
        return Request({"type": "http", "headers": hdrs, "client": ("192.0.2.1", 5000)})

    assert client_ip(req("1.1.1.1, 2.2.2.2, 3.3.3.3"), True, 1) == "3.3.3.3"
    assert client_ip(req("1.1.1.1, 2.2.2.2, 3.3.3.3"), True, 2) == "2.2.2.2"
    assert client_ip(req("9.9.9.9"), True, 2) == "192.0.2.1"       # fewer entries than trusted hops -> do not trust the header
    assert client_ip(req("9.9.9.9"), False, 1) == "192.0.2.1"      # header ignored when the proxy is not trusted
    assert client_ip(req(None), True, 1) == "192.0.2.1"


# ----------------------------------------------------------------------------- role matrix (derived from the real dependencies)
def _operations(app):
    from backend.app.main import API_PREFIX

    def roles_of(route):
        found = []

        def walk(d):
            for sub in d.dependencies:
                found.append(getattr(sub.call, "allowed_roles", None))
                walk(sub)

        walk(route.dependant)
        return next((r for r in found if r), None)

    for r in app.routes:
        if hasattr(r, "original_router"):
            for sub in r.original_router.routes:
                if hasattr(sub, "methods") and roles_of(sub):
                    for m in sub.methods - {"HEAD", "OPTIONS"}:
                        yield m, API_PREFIX + sub.path, roles_of(sub)


def _fill(path: str) -> str:
    import re

    return re.sub(r"\{(\w+)\}", lambda m: "x" if m.group(1) in ("model_id", "group", "name") else "1", path)


def test_role_matrix_viewers_and_analysts_cannot_reach_restricted_endpoints(app):
    c = TestClient(app)
    admin = login(c, "admin@example.com", "AdminPass-12345")
    tokens = {"admin": admin}
    for role in ("analyst", "viewer"):
        h = signup(c, f"{role}-matrix@example.com")
        uid = c.get(f"{API}/auth/me", headers=h).json()["id"]
        assert c.patch(f"{API}/admin/users/{uid}", headers=admin, json={"role": role}).status_code == 200
        tokens[role] = login(c, f"{role}-matrix@example.com", PASSWORD)  # new token carries the new role
    ops = list(_operations(app))
    assert len(ops) >= 15  # 4 admin-only + 13 analyst/admin operations at the time of writing
    denied = allowed_not_403 = 0
    for method, path, roles in ops:
        for role, headers in tokens.items():
            r = c.request(method, _fill(path), headers=headers)
            if role in roles:
                assert r.status_code != 403, f"{role} should be allowed on {method} {path}, got {r.status_code}"
                allowed_not_403 += 1
            else:
                assert r.status_code == 403, f"{role} must be refused on {method} {path}, got {r.status_code}"
                denied += 1
    assert denied >= 20 and allowed_not_403 >= 28  # guards against the loop silently checking nothing
