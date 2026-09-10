"""
test_regression.py — Full regression test suite for Digital Twin AI FastAPI backend.
Covers: Auth, Users, Finance, Study, Habits — all CRUD, validation, auth, and edge cases.
Run: python3 test_regression.py
"""
import uuid
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional

BASE_URL = "http://127.0.0.1:8000"
API = f"{BASE_URL}/api/v1"

TEST_EMAIL = f"regression_test_{uuid.uuid4().hex[:8]}@test.com"
TEST_PASSWORD = "TestPass123!"
TOKEN: Optional[str] = None
USER_ID: Optional[str] = None

PASS_COUNT = 0
FAIL_COUNT = 0
WARN_COUNT = 0
ISSUES = []


def h(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")

def ok(name, detail=""):
    global PASS_COUNT
    PASS_COUNT += 1
    print(f"  PASS  {name}" + (f"  [{detail}]" if detail else ""))

def fail(name, detail="", severity="HIGH"):
    global FAIL_COUNT
    FAIL_COUNT += 1
    ISSUES.append({"test": name, "detail": detail, "severity": severity})
    print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))

def warn(name, detail=""):
    global WARN_COUNT
    WARN_COUNT += 1
    ISSUES.append({"test": name, "detail": detail, "severity": "WARN"})
    print(f"  WARN  {name}" + (f"  [{detail}]" if detail else ""))

def auth_headers():
    return {"Authorization": f"Bearer {TOKEN}"}

def check(name, resp, expected_status, check_fn=None, severity="HIGH"):
    if resp.status_code != expected_status:
        fail(name, f"Expected HTTP {expected_status}, got {resp.status_code}. Body: {resp.text[:250]}", severity)
        return False
    if check_fn:
        try:
            result = check_fn(resp.json())
            if result is False:
                fail(name, "Body assertion returned False", severity)
                return False
        except Exception as e:
            fail(name, f"Body assertion failed: {e}", severity)
            return False
    ok(name, f"HTTP {resp.status_code}")
    return True


# ==============================================================================
# PHASE 1 — HEALTH CHECK
# ==============================================================================
h("PHASE 1 - HEALTH CHECK")

r = requests.get(f"{BASE_URL}/health")
check("GET /health - status ok", r, 200,
      lambda b: b["status"] == "ok" and "version" in b and "app" in b)

r = requests.get(f"{BASE_URL}/api/docs")
check("GET /api/docs - Swagger UI accessible", r, 200, severity="MEDIUM")

r = requests.get(f"{BASE_URL}/api/openapi.json")
check("GET /api/openapi.json - OpenAPI schema accessible", r, 200,
      lambda b: "paths" in b and "info" in b, severity="MEDIUM")


# ==============================================================================
# PHASE 2 - AUTHENTICATION
# ==============================================================================
h("PHASE 2 - AUTHENTICATION")

r = requests.post(f"{API}/auth/register", json={
    "email": TEST_EMAIL, "password": TEST_PASSWORD,
    "name": "Regression Tester", "age": 25, "monthly_income_baseline": 50000.0
})
if check("POST /auth/register - valid registration", r, 201,
         lambda b: "access_token" in b and b.get("token_type") == "bearer" and "user_id" in b):
    body = r.json()
    TOKEN = body["access_token"]
    USER_ID = body["user_id"]

r = requests.post(f"{API}/auth/register", json={
    "email": TEST_EMAIL, "password": TEST_PASSWORD,
    "name": "Dup Tester", "age": 25, "monthly_income_baseline": 0.0
})
check("POST /auth/register - duplicate email -> 409", r, 409)

r = requests.post(f"{API}/auth/register", json={
    "email": "not-an-email", "password": TEST_PASSWORD, "name": "Test", "age": 25
})
check("POST /auth/register - invalid email -> 422", r, 422)

r = requests.post(f"{API}/auth/register", json={
    "email": f"short_{uuid.uuid4().hex[:6]}@test.com", "password": "abc",
    "name": "Test", "age": 25
})
check("POST /auth/register - password too short -> 422", r, 422)

r = requests.post(f"{API}/auth/register", json={
    "email": f"young_{uuid.uuid4().hex[:6]}@test.com", "password": TEST_PASSWORD,
    "name": "Young One", "age": 10
})
check("POST /auth/register - age < 13 -> 422", r, 422)

r = requests.post(f"{API}/auth/register", json={"email": TEST_EMAIL})
check("POST /auth/register - missing fields -> 422", r, 422)

r = requests.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
if check("POST /auth/login - valid credentials -> 200", r, 200,
         lambda b: "access_token" in b and b.get("token_type") == "bearer"):
    TOKEN = r.json()["access_token"]

r = requests.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": "WrongPass999!"})
check("POST /auth/login - wrong password -> 401", r, 401)

r = requests.post(f"{API}/auth/login", json={"email": "nobody@nowhere.com", "password": "SomePass123"})
check("POST /auth/login - non-existent user -> 401", r, 401)

r = requests.post(f"{API}/auth/login", json={"email": TEST_EMAIL})
check("POST /auth/login - missing password -> 422", r, 422)


# ==============================================================================
# PHASE 3 - USER PROFILE
# ==============================================================================
h("PHASE 3 - USER PROFILE")

r = requests.get(f"{API}/users/me", headers=auth_headers())
check("GET /users/me - authenticated -> 200", r, 200,
      lambda b: "id" in b and "email" in b and "profile" in b and
                "preferences" in b and "active_goals" in b and
                "digital_twin_state" in b and "password_hash" not in b)

r = requests.get(f"{API}/users/me")
check("GET /users/me - no token -> 401", r, 401)

r = requests.get(f"{API}/users/me", headers={"Authorization": "Bearer invalid.token.here"})
check("GET /users/me - invalid token -> 401", r, 401)

r = requests.get(f"{API}/users/me", headers={"Authorization": "Basic abc123"})
if r.status_code in [401, 403]:
    ok(f"GET /users/me - malformed auth header -> {r.status_code} (expected 401/403)", f"HTTP {r.status_code}")
else:
    fail("GET /users/me - malformed auth header unexpected status", f"Got {r.status_code}")

r = requests.patch(f"{API}/users/me/profile", headers=auth_headers(),
                   json={"name": "Updated Tester", "age": 26, "occupation": "Engineer"})
check("PATCH /users/me/profile - valid update -> 200", r, 200,
      lambda b: b["profile"]["name"] == "Updated Tester" and b["profile"]["age"] == 26)

r = requests.patch(f"{API}/users/me/profile", headers=auth_headers(),
                   json={"gender": "INVALID_GENDER"})
check("PATCH /users/me/profile - invalid gender enum -> 422", r, 422)

r = requests.patch(f"{API}/users/me/profile", headers=auth_headers(), json={"age": 5})
check("PATCH /users/me/profile - age < 13 -> 422", r, 422)

r = requests.patch(f"{API}/users/me/profile", headers=auth_headers(), json={})
check("PATCH /users/me/profile - empty body (no-op) -> 200", r, 200)

r = requests.patch(f"{API}/users/me/preferences", headers=auth_headers(),
                   json={"dark_mode": False, "currency": "USD", "weekly_report_enabled": False})
check("PATCH /users/me/preferences - valid update -> 200", r, 200,
      lambda b: b["preferences"]["dark_mode"] == False and b["preferences"]["currency"] == "USD")

r = requests.patch(f"{API}/users/me/preferences", json={"dark_mode": True})
check("PATCH /users/me/preferences - no token -> 401", r, 401)


# ==============================================================================
# PHASE 4 - GOALS
# ==============================================================================
h("PHASE 4 - GOALS")

future_date = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()

r = requests.post(f"{API}/users/me/goals", headers=auth_headers(), json={
    "title": "Save 50000 INR", "category": "FINANCE",
    "target_value": 50000, "unit": "INR", "target_date": future_date
})
check("POST /users/me/goals - valid goal -> 201", r, 201,
      lambda b: len(b["active_goals"]) >= 1)

r = requests.get(f"{API}/users/me/goals", headers=auth_headers())
check("GET /users/me/goals - list goals -> 200", r, 200,
      lambda b: isinstance(b, list))

r = requests.post(f"{API}/users/me/goals", headers=auth_headers(), json={
    "title": "Bad Goal", "category": "INVALID_CAT",
    "target_value": 100, "unit": "hrs", "target_date": future_date
})
check("POST /users/me/goals - invalid category -> 422", r, 422)

r = requests.post(f"{API}/users/me/goals", headers=auth_headers(), json={
    "title": "Negative Goal", "category": "STUDY",
    "target_value": -100, "unit": "hrs", "target_date": future_date
})
check("POST /users/me/goals - negative target_value -> 422", r, 422)

r = requests.post(f"{API}/users/me/goals", headers=auth_headers(), json={"title": "Incomplete Goal"})
check("POST /users/me/goals - missing fields -> 422", r, 422)

r = requests.post(f"{API}/users/me/goals", json={
    "title": "Unauth Goal", "category": "STUDY",
    "target_value": 10, "unit": "hrs", "target_date": future_date
})
check("POST /users/me/goals - no token -> 401", r, 401)


# ==============================================================================
# PHASE 5 - FINANCIAL TRANSACTIONS
# ==============================================================================
h("PHASE 5 - FINANCIAL TRANSACTIONS")

r = requests.post(f"{API}/finance/transactions", headers=auth_headers(), json={
    "type": "EXPENSE", "amount": 500.50, "category": "FOOD",
    "description": "Grocery shopping", "is_recurring": False
})
check("POST /finance/transactions - valid expense -> 201", r, 201,
      lambda b: b["type"] == "EXPENSE" and b["category"] == "FOOD" and "id" in b)

r = requests.post(f"{API}/finance/transactions", headers=auth_headers(), json={
    "type": "INCOME", "amount": 75000.00, "category": "SALARY",
    "description": "Monthly salary"
})
check("POST /finance/transactions - valid income -> 201", r, 201,
      lambda b: b["type"] == "INCOME")

r = requests.post(f"{API}/finance/transactions", headers=auth_headers(), json={
    "type": "EXPENSE", "amount": 1200, "category": "HOUSING", "is_recurring": True
})
check("POST /finance/transactions - recurring without frequency -> 422", r, 422)

r = requests.post(f"{API}/finance/transactions", headers=auth_headers(), json={
    "type": "EXPENSE", "amount": 1200, "category": "HOUSING",
    "is_recurring": True, "recurring_frequency": "MONTHLY"
})
check("POST /finance/transactions - recurring with frequency -> 201", r, 201,
      lambda b: b["is_recurring"] == True and b["recurring_frequency"] == "MONTHLY")

r = requests.post(f"{API}/finance/transactions", headers=auth_headers(), json={
    "type": "EXPENSE", "amount": 0, "category": "FOOD"
})
check("POST /finance/transactions - zero amount -> 422", r, 422)

r = requests.post(f"{API}/finance/transactions", headers=auth_headers(), json={
    "type": "EXPENSE", "amount": -100, "category": "FOOD"
})
check("POST /finance/transactions - negative amount -> 422", r, 422)

r = requests.post(f"{API}/finance/transactions", headers=auth_headers(), json={
    "type": "BARTER", "amount": 100, "category": "FOOD"
})
check("POST /finance/transactions - invalid type enum -> 422", r, 422)

r = requests.post(f"{API}/finance/transactions", headers=auth_headers(), json={
    "type": "EXPENSE", "amount": 100, "category": "LUXURY"
})
check("POST /finance/transactions - invalid category -> 422", r, 422)

r = requests.post(f"{API}/finance/transactions", json={
    "type": "EXPENSE", "amount": 100, "category": "FOOD"
})
check("POST /finance/transactions - no token -> 401", r, 401)

r = requests.post(f"{API}/finance/transactions", headers=auth_headers(), json={
    "type": "EXPENSE", "amount": 500, "category": "UTILITIES",
    "is_recurring": True, "recurring_frequency": "EVERY_HOUR"
})
check("POST /finance/transactions - invalid recurring_frequency -> 422", r, 422)

r = requests.get(f"{API}/finance/transactions", headers=auth_headers())
check("GET /finance/transactions - paginated list -> 200", r, 200,
      lambda b: "data" in b and "total" in b and "page" in b and "limit" in b and
                "total_pages" in b and isinstance(b["data"], list))

r = requests.get(f"{API}/finance/transactions?page=1&limit=5", headers=auth_headers())
check("GET /finance/transactions - page/limit params -> 200", r, 200,
      lambda b: b["page"] == 1 and b["limit"] == 5)

r = requests.get(f"{API}/finance/transactions?type=INCOME", headers=auth_headers())
check("GET /finance/transactions - filter by type=INCOME -> 200", r, 200,
      lambda b: all(rec["type"] == "INCOME" for rec in b["data"]))

r = requests.get(f"{API}/finance/transactions?category=FOOD", headers=auth_headers())
check("GET /finance/transactions - filter by category=FOOD -> 200", r, 200,
      lambda b: all(rec["category"] == "FOOD" for rec in b["data"]))

r = requests.get(f"{API}/finance/transactions?page=0", headers=auth_headers())
check("GET /finance/transactions - page=0 -> 422", r, 422)

r = requests.get(f"{API}/finance/transactions?limit=200", headers=auth_headers())
check("GET /finance/transactions - limit=200 > max -> 422", r, 422)

r = requests.get(f"{API}/finance/transactions")
check("GET /finance/transactions - no token -> 401", r, 401)

r = requests.get(f"{API}/finance/analytics/cashflow", headers=auth_headers())
check("GET /finance/analytics/cashflow - default -> 200", r, 200,
      lambda b: isinstance(b, list))

r = requests.get(f"{API}/finance/analytics/cashflow?months_back=12", headers=auth_headers())
check("GET /finance/analytics/cashflow - months_back=12 -> 200", r, 200,
      lambda b: isinstance(b, list))

r = requests.get(f"{API}/finance/analytics/cashflow?months_back=25", headers=auth_headers())
check("GET /finance/analytics/cashflow - months_back=25 > 24 -> 422", r, 422)

r = requests.get(f"{API}/finance/analytics/category", headers=auth_headers())
check("GET /finance/analytics/category - default -> 200", r, 200,
      lambda b: isinstance(b, list))

r = requests.get(f"{API}/finance/analytics/category?months_back=3", headers=auth_headers())
check("GET /finance/analytics/category - months_back=3 -> 200", r, 200,
      lambda b: isinstance(b, list))


# ==============================================================================
# PHASE 6 - STUDY SESSIONS
# ==============================================================================
h("PHASE 6 - STUDY SESSIONS")

r = requests.post(f"{API}/study/sessions", headers=auth_headers(), json={
    "subject": "Mathematics", "study_hours": 2.5,
    "session_type": "DEEP_WORK"
})
check("POST /study/sessions - valid session -> 201", r, 201,
      lambda b: b["subject"] == "Mathematics" and float(b["study_hours"]) == 2.5 and "id" in b)

r = requests.post(f"{API}/study/sessions", headers=auth_headers(), json={
    "subject": "Physics", "study_hours": 1.5, "session_type": "PRACTICE_EXAM",
    "quiz_marks": 18, "max_quiz_marks": 20, "exam_marks": 85, "max_exam_marks": 100
})
check("POST /study/sessions - marks auto-compute pct -> 201", r, 201,
      lambda b: b["quiz_marks_pct"] is not None and float(b["quiz_marks_pct"]) == 90.0
                and b["exam_marks_pct"] is not None and float(b["exam_marks_pct"]) == 85.0)

r = requests.post(f"{API}/study/sessions", headers=auth_headers(), json={
    "subject": "Chemistry", "study_hours": 1.0, "session_type": "REVIEW", "quiz_marks": 15
})
check("POST /study/sessions - quiz_marks without max -> 422", r, 422)

r = requests.post(f"{API}/study/sessions", headers=auth_headers(), json={
    "subject": "History", "study_hours": 1.0, "session_type": "LECTURE", "exam_marks": 70
})
check("POST /study/sessions - exam_marks without max -> 422", r, 422)

r = requests.post(f"{API}/study/sessions", headers=auth_headers(), json={
    "subject": "Art", "study_hours": 0.0, "session_type": "DEEP_WORK"
})
check("POST /study/sessions - study_hours=0 < min -> 422", r, 422)

r = requests.post(f"{API}/study/sessions", headers=auth_headers(), json={
    "subject": "Art", "study_hours": 25.0, "session_type": "DEEP_WORK"
})
check("POST /study/sessions - study_hours>24 -> 422", r, 422)

r = requests.post(f"{API}/study/sessions", headers=auth_headers(), json={
    "subject": "Art", "study_hours": 1.0, "session_type": "NAPPING"
})
check("POST /study/sessions - invalid session_type -> 422", r, 422)

r = requests.post(f"{API}/study/sessions", headers=auth_headers(), json={
    "subject": "Biology", "study_hours": 1.0, "session_type": "REVIEW", "focus_score": 150
})
check("POST /study/sessions - focus_score>100 -> 422", r, 422)

r = requests.post(f"{API}/study/sessions", json={
    "subject": "Math", "study_hours": 1.0, "session_type": "LECTURE"
})
check("POST /study/sessions - no token -> 401", r, 401)

r = requests.get(f"{API}/study/sessions", headers=auth_headers())
check("GET /study/sessions - paginated -> 200", r, 200,
      lambda b: "data" in b and "total" in b and "page" in b and "limit" in b)

r = requests.get(f"{API}/study/sessions?subject=Mathematics", headers=auth_headers())
check("GET /study/sessions - filter by subject -> 200", r, 200,
      lambda b: all(s["subject"] == "Mathematics" for s in b["data"]))

r = requests.get(f"{API}/study/sessions?page=1&limit=5", headers=auth_headers())
check("GET /study/sessions - page/limit -> 200", r, 200,
      lambda b: b["page"] == 1 and b["limit"] == 5)

r = requests.get(f"{API}/study/sessions?page=0", headers=auth_headers())
check("GET /study/sessions - page=0 -> 422", r, 422)

r = requests.get(f"{API}/study/analytics/subject-performance", headers=auth_headers())
check("GET /study/analytics/subject-performance -> 200", r, 200,
      lambda b: isinstance(b, list))

r = requests.get(f"{API}/study/analytics/subject-performance?months_back=3", headers=auth_headers())
check("GET /study/analytics/subject-performance - months_back=3 -> 200", r, 200,
      lambda b: isinstance(b, list))

r = requests.get(f"{API}/study/analytics/subject-performance?months_back=25", headers=auth_headers())
check("GET /study/analytics/subject-performance - months_back=25 -> 422", r, 422)


# ==============================================================================
# PHASE 7 - HABIT TRACKING
# ==============================================================================
h("PHASE 7 - HABIT TRACKING")

r = requests.post(f"{API}/habits/daily-log", headers=auth_headers(), json={
    "sleep_hours": 7.5, "exercise_minutes": 45,
    "water_intake_liters": 2.5, "screen_time_hours": 3.0,
    "mood_rating": 4, "meditation_minutes": 15
})
check("POST /habits/daily-log - valid log -> 200", r, 200,
      lambda b: float(b["sleep_hours"]) == 7.5 and b["exercise_minutes"] == 45 and
                float(b["water_intake_liters"]) == 2.5 and "id" in b and "log_date" in b)

r = requests.post(f"{API}/habits/daily-log", headers=auth_headers(), json={
    "sleep_hours": 8.0, "exercise_minutes": 60,
    "water_intake_liters": 3.0, "screen_time_hours": 2.0, "mood_rating": 5
})
check("POST /habits/daily-log - upsert same day -> 200", r, 200,
      lambda b: float(b["sleep_hours"]) == 8.0)

r = requests.post(f"{API}/habits/daily-log", headers=auth_headers(), json={
    "sleep_hours": 25.0, "exercise_minutes": 30, "water_intake_liters": 2.0, "screen_time_hours": 2.0
})
check("POST /habits/daily-log - sleep_hours>24 -> 422", r, 422)

r = requests.post(f"{API}/habits/daily-log", headers=auth_headers(), json={
    "sleep_hours": -1, "exercise_minutes": 30, "water_intake_liters": 2.0, "screen_time_hours": 2.0
})
check("POST /habits/daily-log - negative sleep_hours -> 422", r, 422)

r = requests.post(f"{API}/habits/daily-log", headers=auth_headers(), json={
    "sleep_hours": 7.0, "exercise_minutes": 30, "water_intake_liters": 2.0,
    "screen_time_hours": 2.0, "mood_rating": 10
})
check("POST /habits/daily-log - mood_rating>5 -> 422", r, 422)

r = requests.post(f"{API}/habits/daily-log", headers=auth_headers(), json={
    "sleep_hours": 7.0, "exercise_minutes": 30, "water_intake_liters": 2.0,
    "screen_time_hours": 2.0, "mood_rating": 0
})
check("POST /habits/daily-log - mood_rating=0 < 1 -> 422", r, 422)

r = requests.post(f"{API}/habits/daily-log", headers=auth_headers(), json={
    "sleep_hours": 7.0, "exercise_minutes": 30, "water_intake_liters": 25.0, "screen_time_hours": 2.0
})
check("POST /habits/daily-log - water>20 -> 422", r, 422)

r = requests.post(f"{API}/habits/daily-log", headers=auth_headers(), json={"sleep_hours": 7.0})
check("POST /habits/daily-log - missing required fields -> 422", r, 422)

r = requests.post(f"{API}/habits/daily-log", json={
    "sleep_hours": 7.0, "exercise_minutes": 30, "water_intake_liters": 2.0, "screen_time_hours": 2.0
})
check("POST /habits/daily-log - no token -> 401", r, 401)

r = requests.get(f"{API}/habits/daily-log", headers=auth_headers())
check("GET /habits/daily-log - paginated -> 200", r, 200,
      lambda b: "data" in b and "total" in b and isinstance(b["data"], list))

r = requests.get(f"{API}/habits/daily-log?page=1&limit=5", headers=auth_headers())
check("GET /habits/daily-log - page/limit -> 200", r, 200,
      lambda b: b["page"] == 1 and b["limit"] == 5)

r = requests.get(f"{API}/habits/daily-log?page=0", headers=auth_headers())
check("GET /habits/daily-log - page=0 -> 422", r, 422)

r = requests.get(f"{API}/habits/daily-log?limit=200", headers=auth_headers())
check("GET /habits/daily-log - limit=200 > 100 -> 422", r, 422)

r = requests.get(f"{API}/habits/analytics/kmeans-features", headers=auth_headers())
check("GET /habits/analytics/kmeans-features - default -> 200", r, 200,
      lambda b: isinstance(b, list))

r = requests.get(f"{API}/habits/analytics/kmeans-features?days=7", headers=auth_headers())
check("GET /habits/analytics/kmeans-features - days=7 -> 200", r, 200,
      lambda b: isinstance(b, list))

r = requests.get(f"{API}/habits/analytics/kmeans-features?days=3", headers=auth_headers())
check("GET /habits/analytics/kmeans-features - days=3 < 7 -> 422", r, 422)

r = requests.get(f"{API}/habits/analytics/kmeans-features?days=400", headers=auth_headers())
check("GET /habits/analytics/kmeans-features - days=400 > 365 -> 422", r, 422)


# ==============================================================================
# PHASE 8 - SECURITY TESTS
# ==============================================================================
h("PHASE 8 - SECURITY TESTS")

r = requests.post(f"{API}/auth/login", json={"email": "' OR '1'='1", "password": "irrelevant"})
if r.status_code in [422, 401]:
    ok(f"SECURITY - SQL injection in email -> {r.status_code} (rejected)", f"HTTP {r.status_code}")
else:
    fail("SECURITY - SQL injection not rejected", f"Got HTTP {r.status_code}", "CRITICAL")

r = requests.post(f"{API}/auth/register", json={
    "email": f"xss_{uuid.uuid4().hex[:6]}@test.com", "password": "ValidPass123!",
    "name": "<script>alert('xss')</script>", "age": 25
})
if r.status_code in [201, 422]:
    ok(f"SECURITY - XSS in name handled safely", f"HTTP {r.status_code}")
else:
    fail("SECURITY - XSS payload caused unexpected error", f"HTTP {r.status_code}", "HIGH")

bad_token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiI2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NiIsImV4cCI6MX0.bad"
r = requests.get(f"{API}/users/me", headers={"Authorization": f"Bearer {bad_token}"})
check("SECURITY - tampered JWT -> 401", r, 401)

r = requests.get(f"{API}/finance/transactions", headers=auth_headers())
if r.status_code == 200:
    data = r.json()["data"]
    leaked = [rec for rec in data if rec.get("user_id") != USER_ID]
    if leaked:
        fail("SECURITY - data isolation broken: found another user's record", str(leaked[0])[:100], "CRITICAL")
    else:
        ok("SECURITY - data isolation intact (all records belong to current user)")

r = requests.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
if r.status_code == 200:
    if "password_hash" in r.text or "password_hash" in r.text:
        fail("SECURITY - password_hash exposed in login response", severity="CRITICAL")
    else:
        ok("SECURITY - password not exposed in login response")

r = requests.get(f"{API}/users/me", headers=auth_headers())
if r.status_code == 200:
    if "password_hash" in r.text:
        fail("SECURITY - password_hash exposed in /users/me response", severity="CRITICAL")
    else:
        ok("SECURITY - password_hash not in /users/me response")

r = requests.post(f"{API}/finance/transactions", headers=auth_headers(), json={
    "type": "EXPENSE", "amount": -99999, "category": "FOOD"
})
check("SECURITY - negative amount injection -> 422", r, 422)

r = requests.post(f"{API}/finance/transactions", headers=auth_headers(), json={
    "type": "EXPENSE", "amount": 10, "category": "OTHER",
    "description": "A" * 1000
})
check("SECURITY - description > 255 chars -> 422", r, 422)


# ==============================================================================
# PHASE 9 - EDGE CASES
# ==============================================================================
h("PHASE 9 - EDGE CASES")

r = requests.get(f"{API}/finance/transactions?page=9999&limit=20", headers=auth_headers())
check("EDGE - page beyond total -> 200 empty data", r, 200,
      lambda b: isinstance(b["data"], list))

r = requests.get(f"{API}/finance/analytics/cashflow?months_back=0", headers=auth_headers())
check("EDGE - cashflow months_back=0 -> 422", r, 422)

r = requests.post(f"{API}/study/sessions", headers=auth_headers(), json={
    "subject": "Boundary Test", "study_hours": 0.1, "session_type": "REVIEW"
})
check("EDGE - study_hours=0.1 (exact min boundary) -> 201", r, 201)

r = requests.post(f"{API}/study/sessions", headers=auth_headers(), json={
    "subject": "Max Hours", "study_hours": 24.0, "session_type": "RESEARCH"
})
check("EDGE - study_hours=24.0 (exact max boundary) -> 201", r, 201)

r = requests.post(f"{API}/habits/daily-log", headers=auth_headers(), json={
    "sleep_hours": 0, "exercise_minutes": 0, "water_intake_liters": 0, "screen_time_hours": 0
})
check("EDGE - habit all zeros (ge=0 allowed) -> 200", r, 200)

r = requests.post(f"{API}/finance/transactions", headers=auth_headers(), json={
    "type": "SAVINGS_DEPOSIT", "amount": 10000, "category": "SAVINGS"
})
check("EDGE - type=SAVINGS_DEPOSIT -> 201", r, 201)

r = requests.post(f"{API}/finance/transactions", headers=auth_headers(), json={
    "type": "INVESTMENT", "amount": 5000, "category": "INVESTMENT"
})
check("EDGE - type=INVESTMENT -> 201", r, 201)

r = requests.post(f"{API}/study/sessions", headers=auth_headers(), json={
    "subject": "Homework", "study_hours": 1.5, "session_type": "ASSIGNMENT"
})
check("EDGE - session_type=ASSIGNMENT -> 201", r, 201)

past_date = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
r = requests.post(f"{API}/finance/transactions", headers=auth_headers(), json={
    "type": "EXPENSE", "amount": 250, "category": "ENTERTAINMENT",
    "transaction_date": past_date
})
check("EDGE - custom transaction_date (7 days ago) -> 201", r, 201,
      lambda b: "transaction_date" in b)

for cat in ["FINANCE", "STUDY", "HABIT", "FITNESS", "CAREER"]:
    r = requests.post(f"{API}/users/me/goals", headers=auth_headers(), json={
        "title": f"{cat} Regression Goal", "category": cat,
        "target_value": 100, "unit": "units", "target_date": future_date
    })
    check(f"EDGE - goal category={cat} -> 201", r, 201)


# ==============================================================================
# PHASE 10 - RESPONSE FORMAT VALIDATION
# ==============================================================================
h("PHASE 10 - RESPONSE FORMAT VALIDATION")

r = requests.post(f"{API}/finance/transactions", headers=auth_headers(), json={
    "type": "EXPENSE", "amount": 1, "category": "OTHER"
})
if r.status_code == 201:
    b = r.json()
    required = ["id", "user_id", "type", "amount", "category", "is_recurring",
                "transaction_date", "created_at"]
    missing = [f for f in required if f not in b]
    if missing:
        fail(f"RESPONSE FORMAT - finance record missing: {missing}", severity="MEDIUM")
    else:
        ok("RESPONSE FORMAT - finance record has all required fields")

r = requests.post(f"{API}/study/sessions", headers=auth_headers(), json={
    "subject": "Format Test", "study_hours": 1.0, "session_type": "LECTURE"
})
if r.status_code == 201:
    b = r.json()
    required = ["id", "user_id", "subject", "study_hours", "session_type",
                "session_date", "created_at"]
    missing = [f for f in required if f not in b]
    if missing:
        fail(f"RESPONSE FORMAT - study record missing: {missing}", severity="MEDIUM")
    else:
        ok("RESPONSE FORMAT - study record has all required fields")

r = requests.post(f"{API}/habits/daily-log", headers=auth_headers(), json={
    "sleep_hours": 7, "exercise_minutes": 30, "water_intake_liters": 2.0, "screen_time_hours": 3.0
})
if r.status_code == 200:
    b = r.json()
    required = ["id", "user_id", "sleep_hours", "exercise_minutes",
                "water_intake_liters", "screen_time_hours",
                "burnout_risk_cluster", "log_date", "created_at"]
    missing = [f for f in required if f not in b]
    if missing:
        fail(f"RESPONSE FORMAT - habit record missing: {missing}", severity="MEDIUM")
    else:
        ok("RESPONSE FORMAT - habit record has all required fields")

r = requests.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
if r.status_code == 200:
    b = r.json()
    for field in ["access_token", "token_type", "user_id", "email"]:
        if field not in b:
            fail(f"RESPONSE FORMAT - token response missing '{field}'")
        else:
            ok(f"RESPONSE FORMAT - token response has '{field}'")


# ==============================================================================
# PHASE 11 - HTTP METHOD ENFORCEMENT
# ==============================================================================
h("PHASE 11 - HTTP METHOD ENFORCEMENT")

r = requests.get(f"{API}/auth/register")
check("METHOD - GET on POST-only /auth/register -> 405", r, 405)

r = requests.delete(f"{API}/users/me", headers=auth_headers())
if r.status_code in [404, 405]:
    ok(f"METHOD - DELETE /users/me -> {r.status_code} (expected 404/405)", f"HTTP {r.status_code}")
else:
    warn(f"METHOD - DELETE /users/me unexpected status", f"Got {r.status_code}")

r = requests.put(f"{API}/finance/transactions", headers=auth_headers())
if r.status_code in [404, 405, 422]:
    ok(f"METHOD - PUT /finance/transactions -> {r.status_code}")
else:
    warn(f"METHOD - PUT /finance/transactions unexpected", f"Got {r.status_code}")


# ==============================================================================
# FINAL REPORT
# ==============================================================================
total = PASS_COUNT + FAIL_COUNT + WARN_COUNT
print(f"\n{'='*60}")
print(f"  REGRESSION TEST REPORT")
print(f"{'='*60}")
print(f"  Total Tests: {total}")
print(f"  PASS:  {PASS_COUNT}")
print(f"  FAIL:  {FAIL_COUNT}")
print(f"  WARN:  {WARN_COUNT}")
print(f"{'='*60}")
if ISSUES:
    print("\n  ISSUES FOUND:")
    for i in ISSUES:
        print(f"  [{i['severity']}] {i['test']}")
        if i["detail"]:
            print(f"       -> {i['detail']}")
if FAIL_COUNT == 0:
    print("\n  ALL TESTS PASSED")
else:
    print(f"\n  {FAIL_COUNT} test(s) FAILED - review issues above")
print()
