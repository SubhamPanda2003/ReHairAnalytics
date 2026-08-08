"""Seed a single temp user + session token for UI testing; print token."""
import os, uuid, sys
from datetime import datetime, timezone, timedelta
from dotenv import dotenv_values
from pymongo import MongoClient

env = dotenv_values("/app/backend/.env")
db = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]

if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
    print(db.users.delete_many({"user_id": {"$regex": "^TEST_ui-scan5-"}}).deleted_count)
    print(db.user_sessions.delete_many({"session_token": {"$regex": "^test_session_scan5_"}}).deleted_count)
    raise SystemExit

stamp = int(datetime.now(timezone.utc).timestamp())
uid = f"TEST_ui-scan5-{stamp}"
token = f"test_session_scan5_{stamp}_{uuid.uuid4().hex[:6]}"
db.users.insert_one({"user_id": uid, "email": f"TEST_ui+scan5+{stamp}@example.com",
                     "name": "TEST scan5", "picture": "",
                     "created_at": datetime.now(timezone.utc).isoformat()})
db.user_sessions.insert_one({"user_id": uid, "session_token": token,
                             "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                             "created_at": datetime.now(timezone.utc).isoformat()})
print(token)
