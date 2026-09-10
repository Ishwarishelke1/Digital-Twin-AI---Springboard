"""
tests/conftest.py — Registers Beanie's class-level query metadata (needed for
expressions like `User.email == value`) once for the whole test session, against a
lazily-created Motor client that is never actually connected to.

Motor clients are lazy: constructing one and calling init_beanie() against it only
registers local class metadata (document settings, index definitions, the
`Model.field` expression descriptors) — no network I/O happens unless a real query is
awaited against it. Every test still mocks out the actual I/O calls (.find/.find_one/
.insert/.get/.aggregate/get_motor_collection) individually, exactly as before; this
fixture only makes `Model.field == value`-style expressions resolve instead of raising
AttributeError, which several service functions (create_user, authenticate_user,
delete_user, etc.) use internally.
"""
import asyncio

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from models.activity import UserActivity
from models.ai_recommendation import AIRecommendation
from models.feedback import AssistantFeedback
from models.finance import FinancialRecord
from models.habit import HabitTracking
from models.simulation import Recommendation, Simulation
from models.study import StudyActivity
from models.user import User


async def _init():
    client = AsyncIOMotorClient("mongodb://localhost:27017", serverSelectionTimeoutMS=100)
    await init_beanie(
        database=client.test_db,
        document_models=[
            User, FinancialRecord, StudyActivity, HabitTracking, UserActivity, Simulation, Recommendation,
            AssistantFeedback, AIRecommendation,
        ],
    )


asyncio.run(_init())
