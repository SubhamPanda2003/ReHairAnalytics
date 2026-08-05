"""Shared test fixtures. Seed a MongoDB user + session_token for auth."""
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


@pytest.fixture(scope="session")
def api_base():
    return BASE_URL


@pytest.fixture(scope="session")
def mongo_db():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="session")
def seeded_user(mongo_db):
    """Insert a test user + session_token, return (user_id, token)."""
    stamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    user_id = f"test-user-{stamp}-{uuid.uuid4().hex[:6]}"
    token = f"test_session_{stamp}_{uuid.uuid4().hex[:6]}"
    mongo_db.users.insert_one({
        "user_id": user_id,
        "email": f"qa+{stamp}@example.com",
        "name": "QA User",
        "picture": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mongo_db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    yield user_id, token
    # cleanup at end
    mongo_db.users.delete_many({"user_id": user_id})
    mongo_db.user_sessions.delete_many({"user_id": user_id})
    mongo_db.profiles.delete_many({"user_id": user_id})
    mongo_db.tracking_sessions.delete_many({"user_id": user_id})
    mongo_db.images.delete_many({"user_id": user_id})
    mongo_db.analysis.delete_many({"user_id": user_id})


@pytest.fixture(scope="session")
def auth_client(seeded_user):
    _, token = seeded_user
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="session")
def anon_client():
    return requests.Session()
