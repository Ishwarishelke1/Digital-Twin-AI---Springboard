"""
One-off script: wipes and re-seeds zohaib@gmail.com's finance/study/habit/goal
data in the live Atlas database with deliberately varied data — engineered so
every Milestone-2 engine shows both a positive and a negative signal, for a
demo/presentation account. Run once: python3 scripts/seed_zohaib.py
"""
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from dotenv import load_dotenv
from pymongo import MongoClient
from bson import Decimal128

# Import from the package root so this runs the same way as the other scripts
# (python3 scripts/seed_zohaib.py from backend/).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.db_guard import require_non_production  # noqa: E402

load_dotenv()

# This script calls delete_many() on three collections and overwrites active_goals.
# Refuse to do that to a production database unless explicitly authorised.
require_non_production("wipe and re-seed zohaib@gmail.com's finance/study/habit/goal data")

client = MongoClient(os.environ["MONGODB_URI"])
db = client[os.environ["MONGODB_DB_NAME"]]

user = db.users.find_one({"email": "zohaib@gmail.com"})
if not user:
    raise SystemExit("User not found")

USER_ID = user["_id"]
NOW = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)

random.seed(7)


def D(value):
    return Decimal128(str(round(float(value), 2)))


# ─── Wipe existing seeded data for this user ─────────────────────────────────
db.financial_records.delete_many({"user_id": USER_ID})
db.study_activities.delete_many({"user_id": USER_ID})
db.habit_trackings.delete_many({"user_id": USER_ID})

# ─── FINANCE: rising-but-noisy income, one bad expense month ─────────────────
# Monthly salary, deliberately noisy (not a perfectly flat/clean line) so the
# linear-regression forecast has a real slope and R² < 1, not a trivial flat fit.
MONTHLY_INCOME = [21000, 22500, 24000, 23500, 26000, 27500]  # oldest -> newest
MONTHLY_EXPENSE = [15000, 15500, 25000, 16000, 17000, 18000]  # month index 2 = spike (negative signal)

finance_docs = []
for i in range(6):
    month_date = NOW - timedelta(days=(5 - i) * 30)
    finance_docs.append({
        "user_id": USER_ID, "type": "INCOME", "amount": D(MONTHLY_INCOME[i]),
        "category": "SALARY", "description": "Monthly salary", "is_recurring": True,
        "recurring_frequency": "MONTHLY", "linked_goal_id": None,
        "transaction_date": month_date, "created_at": month_date,
    })

EXPENSE_CATS = ["FOOD", "HOUSING", "UTILITIES", "TRANSPORT", "ENTERTAINMENT"]
for i in range(6):
    month_date = NOW - timedelta(days=(5 - i) * 30)
    target = MONTHLY_EXPENSE[i]
    remaining = target
    for j, cat in enumerate(EXPENSE_CATS):
        share = remaining if j == len(EXPENSE_CATS) - 1 else round(target * random.uniform(0.1, 0.3))
        share = max(100, min(share, remaining))
        remaining -= share
        d = month_date - timedelta(days=random.randint(0, 25))
        finance_docs.append({
            "user_id": USER_ID, "type": "EXPENSE", "amount": D(share),
            "category": "HEALTH" if (i == 2 and cat == "ENTERTAINMENT") else cat,
            "description": "Emergency medical expense" if (i == 2 and cat == "ENTERTAINMENT") else None,
            "is_recurring": False, "recurring_frequency": None, "linked_goal_id": None,
            "transaction_date": d, "created_at": d,
        })
        if remaining <= 0:
            break

db.financial_records.insert_many(finance_docs)

# ─── GOALS: one clearly on-track, one clearly off-track, one non-finance ─────
new_goals = [
    {
        "goal_id": str(uuid.uuid4()), "title": "Emergency Fund", "category": "FINANCE",
        "target_value": D(15000), "current_value": D(3000), "unit": "USD",
        "target_date": NOW + timedelta(days=180), "created_at": NOW - timedelta(days=150),
    },
    {
        "goal_id": str(uuid.uuid4()), "title": "Buy a Car", "category": "FINANCE",
        "target_value": D(500000), "current_value": D(5000), "unit": "USD",
        "target_date": NOW + timedelta(days=60), "created_at": NOW - timedelta(days=90),
    },
    {
        "goal_id": str(uuid.uuid4()), "title": "Finish DSA Course", "category": "STUDY",
        "target_value": D(100), "current_value": D(62), "unit": "percent",
        "target_date": NOW + timedelta(days=45), "created_at": NOW - timedelta(days=60),
    },
]
db.users.update_one({"_id": USER_ID}, {"$set": {"active_goals": new_goals}})

# ─── STUDY: 5 subjects, deliberately split into strong / weak performers ─────
# subject: (focus_range, exam_start, exam_end) — exam trends linearly from
# start -> end across the 70-day window (rising = positive subject, falling = negative).
SUBJECT_PROFILES = {
    "Maths":     {"focus": (78, 92), "exam": (65, 92)},   # improving
    "Physics":   {"focus": (70, 82), "exam": (78, 82)},   # stable/good
    "DSA":       {"focus": (55, 72), "exam": (60, 75)},   # mild improvement
    "Chemistry": {"focus": (40, 80), "exam": (85, 52)},   # declining
    "History":   {"focus": (28, 46), "exam": (38, 56)},   # weak throughout
}
SESSION_TYPES = ["DEEP_WORK", "REVIEW", "LECTURE", "PRACTICE_EXAM", "ASSIGNMENT", "RESEARCH"]

study_docs = []
WINDOW_DAYS = 70
for day_offset in range(WINDOW_DAYS, -1, -1):
    d = NOW - timedelta(days=day_offset)
    progress = 1 - (day_offset / WINDOW_DAYS)  # 0 (oldest) -> 1 (newest)
    if random.random() < 0.65:
        subject = random.choice(list(SUBJECT_PROFILES.keys()))
        prof = SUBJECT_PROFILES[subject]
        foc_lo, foc_hi = prof["focus"]
        exam_start, exam_end = prof["exam"]

        focus = foc_lo + (foc_hi - foc_lo) * progress + random.uniform(-4, 4)
        hours = round(random.uniform(1, 3.5), 1)
        has_exam = random.random() < 0.25
        exam_pct = exam_start + (exam_end - exam_start) * progress + random.uniform(-4, 4)

        doc = {
            "user_id": USER_ID, "subject": subject, "study_hours": D(hours),
            "session_type": random.choice(SESSION_TYPES),
            "quiz_marks": None, "max_quiz_marks": None, "quiz_marks_pct": None,
            "exam_marks": None, "max_exam_marks": None, "exam_marks_pct": None,
            "focus_score": int(max(0, min(100, focus))),
            "linked_goal_id": None, "session_date": d, "created_at": d,
        }
        if has_exam:
            pct = max(0, min(100, exam_pct))
            doc["exam_marks"] = D(pct)
            doc["max_exam_marks"] = D(100)
            doc["exam_marks_pct"] = D(pct)
        study_docs.append(doc)

db.study_activities.insert_many(study_docs)

# ─── HABITS: last 30 days = mixed positive/negative metrics + missed days;
#     an earlier 15-day unbroken run gives a longer "longest streak" than the
#     current one, and the most recent 6 days are an unbroken current streak. ─
habit_docs = []

# Earlier block (-89 to -75): 15 consecutive logged days -> longest_streak candidate
for day_offset in range(89, 74, -1):
    d = (NOW - timedelta(days=day_offset)).replace(hour=0, minute=0, second=0, microsecond=0)
    habit_docs.append({
        "user_id": USER_ID,
        "sleep_hours": D(round(random.uniform(6.0, 8.0), 1)),
        "exercise_minutes": random.randint(10, 40),
        "water_intake_liters": D(round(random.uniform(1.5, 2.5), 1)),
        "screen_time_hours": D(round(random.uniform(4, 7), 1)),
        "mood_rating": random.randint(2, 5),
        "meditation_minutes": None,
        "productivity_score_computed": None, "lifestyle_score_computed": None,
        "burnout_risk_cluster": "UNKNOWN", "log_date": d, "created_at": d,
    })

# Sparse middle block (-74 to -30): gaps, unremarkable values (outside the
# 30-day analytics window, so its values don't affect current scoring)
for day_offset in range(74, 29, -1):
    if random.random() < 0.5:
        continue
    d = (NOW - timedelta(days=day_offset)).replace(hour=0, minute=0, second=0, microsecond=0)
    habit_docs.append({
        "user_id": USER_ID,
        "sleep_hours": D(round(random.uniform(5.5, 8.5), 1)),
        "exercise_minutes": random.randint(0, 45),
        "water_intake_liters": D(round(random.uniform(1.0, 2.8), 1)),
        "screen_time_hours": D(round(random.uniform(3, 9), 1)),
        "mood_rating": random.randint(1, 5),
        "meditation_minutes": None,
        "productivity_score_computed": None, "lifestyle_score_computed": None,
        "burnout_risk_cluster": "UNKNOWN", "log_date": d, "created_at": d,
    })

# Last 30 days (-29 to -6): the analytics window. Skip 5 scattered days
# (-> missed_habits), rest get consistently GOOD sleep + water but
# consistently POOR exercise + screen_time -> clean 2 positive / 2 negative split.
skip_days = set(random.sample(range(6, 30), 5))
for day_offset in range(29, 5, -1):
    if day_offset in skip_days:
        continue
    d = (NOW - timedelta(days=day_offset)).replace(hour=0, minute=0, second=0, microsecond=0)
    habit_docs.append({
        "user_id": USER_ID,
        "sleep_hours": D(round(random.uniform(7.0, 8.5), 1)),          # positive (healthy 7-9h)
        "exercise_minutes": random.randint(5, 20),                      # negative (target 30)
        "water_intake_liters": D(round(random.uniform(2.1, 2.8), 1)),  # positive (target 2.0)
        "screen_time_hours": D(round(random.uniform(7.8, 9.5), 1)),    # negative (healthy max 6)
        "mood_rating": random.randint(2, 4),
        "meditation_minutes": random.choice([None, 10, 15]),
        "productivity_score_computed": None, "lifestyle_score_computed": None,
        "burnout_risk_cluster": "UNKNOWN", "log_date": d, "created_at": d,
    })

# Last 6 days (-5 to 0): unbroken, currently active streak.
for day_offset in range(5, -1, -1):
    d = (NOW - timedelta(days=day_offset)).replace(hour=0, minute=0, second=0, microsecond=0)
    habit_docs.append({
        "user_id": USER_ID,
        "sleep_hours": D(round(random.uniform(7.2, 8.2), 1)),
        "exercise_minutes": random.randint(10, 25),
        "water_intake_liters": D(round(random.uniform(2.2, 2.7), 1)),
        "screen_time_hours": D(round(random.uniform(7.8, 9.0), 1)),
        "mood_rating": random.randint(3, 5),
        "meditation_minutes": random.choice([None, 10, 20]),
        "productivity_score_computed": None, "lifestyle_score_computed": None,
        "burnout_risk_cluster": "UNKNOWN", "log_date": d, "created_at": d,
    })

db.habit_trackings.insert_many(habit_docs)

print(f"Finance records: {len(finance_docs)}")
print(f"Study records:   {len(study_docs)}")
print(f"Habit records:   {len(habit_docs)}")
print(f"Goals set:       {len(new_goals)}")
