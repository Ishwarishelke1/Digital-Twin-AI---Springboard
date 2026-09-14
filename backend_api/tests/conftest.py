"""
tests/conftest.py — Registers Beanie's class-level query metadata (needed for
expressions like `User.email == value`) once for the whole test session, against a
Motor client that never actually reaches a real server.

Motor clients are themselves lazy — constructing one does no I/O. But
`init_beanie()` is not: as of beanie==1.26.0 (pinned in requirements.txt),
`Initializer.init_document()` unconditionally calls `database.command({"buildInfo": 1})`
to detect the server version, and `Initializer.init_indexes()` calls
`collection.index_information()` / `collection.create_indexes()` to sync each
model's declared indexes — all real network calls, made for every model, regardless
of whether any test ever awaits a query. Left unpatched, importing this module
requires a reachable MongoDB-compatible server purely to finish import, which
defeats the "zero live DB connection" property this suite is meant to have (see
CLAUDE.md's Testing section) and makes the whole file fail to collect if nothing is
listening on `MONGODB_URI`.

So those three specific Motor calls are stubbed for the duration of init_beanie()
only: `command` returns a fake buildInfo, `index_information` returns no existing
indexes, and `create_indexes` returns an empty list. That's enough for Beanie to
register document settings, index definitions, and the `Model.field` expression
descriptors — no real socket is ever opened. Every test still mocks out the actual
I/O calls (.find/.find_one/.insert/.get/.aggregate/get_motor_collection) individually
per-test, exactly as before; this fixture only makes `Model.field == value`-style
expressions resolve instead of raising AttributeError, which several service
functions (create_user, authenticate_user, delete_user, etc.) use internally.
"""
import asyncio
from unittest.mock import AsyncMock, patch

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase

from models.activity import UserActivity
from models.ai_recommendation import AIRecommendation
from models.feedback import AssistantFeedback
from models.finance import FinancialRecord
from models.habit import HabitTracking
from models.simulation import Recommendation, Simulation
from models.study import StudyActivity
from models.user import User


async def _init():
    # No real server is ever contacted: serverSelectionTimeoutMS is irrelevant here
    # because every Motor call init_beanie() makes is stubbed below.
    client = AsyncIOMotorClient("mongodb://localhost:27017", serverSelectionTimeoutMS=100)
    with (
        patch.object(AsyncIOMotorDatabase, "command", AsyncMock(return_value={"version": "7.0.0"})),
        patch.object(AsyncIOMotorCollection, "index_information", AsyncMock(return_value={})),
        patch.object(AsyncIOMotorCollection, "create_indexes", AsyncMock(return_value=[])),
    ):
        await init_beanie(
            database=client.test_db,
            document_models=[
                User, FinancialRecord, StudyActivity, HabitTracking, UserActivity, Simulation, Recommendation,
                AssistantFeedback, AIRecommendation,
            ],
        )


asyncio.run(_init())
