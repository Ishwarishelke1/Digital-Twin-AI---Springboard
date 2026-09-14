"""
tests/test_routes_auth_enforcement.py — Confirms every protected router actually
rejects unauthenticated requests, and that public routes don't. This is the one gap
none of the other tests cover: a route-level guarantee, not a unit test of the auth
dependency in isolation (already covered by tests/test_auth_dependency.py).

No DB/network needed: FastAPI's OAuth2PasswordBearer dependency rejects a request with
no (or a malformed) Authorization header before any service/DB code ever runs, and
Pydantic request validation runs before route handlers too — so this whole sweep is
safe to run with the real `app` object and zero mocking.
"""
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)

# One representative protected endpoint per router — exactly what let the old
# simulation.py router (fixed earlier this session) ship with no auth at all
# undetected: nothing ever swept the API surface like this before.
PROTECTED_ENDPOINTS = [
    ("GET", "/api/v1/users/me"),
    ("GET", "/api/v1/finance/transactions"),
    ("GET", "/api/v1/study/sessions"),
    ("GET", "/api/v1/habits/daily-log"),
    ("GET", "/api/v1/activity"),
    ("GET", "/api/v1/forecast/summary"),
    ("GET", "/api/v1/productivity/score"),
    ("GET", "/api/v1/habit-analytics/summary"),
    ("GET", "/api/v1/trends/summary"),
    ("GET", "/api/v1/simulation/history"),
    ("POST", "/api/v1/simulation/finance/scenarios"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/users/me/change-password"),
]


def test_every_protected_endpoint_rejects_missing_auth_header():
    failures = []
    for method, path in PROTECTED_ENDPOINTS:
        response = client.request(method, path, json={} if method == "POST" else None)
        if response.status_code != 401:
            failures.append(f"{method} {path} -> {response.status_code} (expected 401)")
    assert not failures, "\n".join(failures)


def test_every_protected_endpoint_rejects_garbage_bearer_token():
    failures = []
    headers = {"Authorization": "Bearer not-a-real-token"}
    for method, path in PROTECTED_ENDPOINTS:
        response = client.request(method, path, headers=headers, json={} if method == "POST" else None)
        if response.status_code != 401:
            failures.append(f"{method} {path} -> {response.status_code} (expected 401)")
    assert not failures, "\n".join(failures)


def test_public_routes_do_not_require_auth():
    # /health never requires auth and always succeeds.
    assert client.get("/health").status_code == 200

    # /auth/register and /auth/login are public — an invalid/empty body should fail
    # Pydantic validation (422), never the auth guard (401), since they have none.
    assert client.post("/api/v1/auth/register", json={}).status_code != 401
    assert client.post("/api/v1/auth/login", json={}).status_code != 401
