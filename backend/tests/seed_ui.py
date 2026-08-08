"""Seed users/sessions for frontend (Playwright) testing of role-gated pages.

Creates:
  - patient        : plain user (role=user)
  - derm_approved  : registered + approved dermatologist
  - derm_pending   : registered, pending (for /admin approve button)
  - super_admin    : email iampandasubham@gmail.com
  - fresh          : plain user with no derm profile (for /derm registration form)

Writes tokens to /app/test_reports/ui_seed.json
"""
import json
import os
import uuid
from datetime import datetime, timezone, timedelta

import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
db = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
    os.environ.get("DB_NAME", "test_database")
]
SUPER_ADMIN_EMAIL = "iampandasubham@gmail.com"


def seed(label, email=None):
    stamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    uid = f"TEST_ui-{label}-{stamp}-{uuid.uuid4().hex[:6]}"
    token = f"test_session_ui_{label}_{stamp}_{uuid.uuid4().hex[:6]}"
    db.users.insert_one({
        "user_id": uid,
        "email": email or f"TEST_ui+{label}+{stamp}@example.com",
        "name": f"TEST {label}",
        "picture": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    db.user_sessions.insert_one({
        "user_id": uid, "session_token": token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return {"user_id": uid, "token": token, "sess": s}


def main():
    out = {}
    for label, email in [("patient", None), ("dermok", None), ("dermpending", None),
                         ("superadmin", SUPER_ADMIN_EMAIL), ("fresh", None)]:
        out[label] = seed(label, email)

    dermok_payload = {
        "name": "TEST Dr. Meera Sharma", "specialty": "Trichology & Hair Restoration",
        "years_experience": 12, "bio": "TEST profile for UI automation. Focused on androgenetic alopecia.",
        "photo": "", "meeting_link": "https://meet.google.com/test-ui-derm", "price": "$60 / session",
    }
    r = out["dermok"]["sess"].post(f"{API}/derm/register", json=dermok_payload)
    assert r.status_code == 200, r.text
    r = out["superadmin"]["sess"].post(
        f"{API}/admin/dermatologists/{out['dermok']['user_id']}/approve")
    assert r.status_code == 200, r.text

    pend_payload = dict(dermok_payload)
    pend_payload.update({"name": "TEST Dr. Pending Patel", "specialty": "Dermatology",
                         "meeting_link": "https://meet.google.com/test-ui-pending"})
    r = out["dermpending"]["sess"].post(f"{API}/derm/register", json=pend_payload)
    assert r.status_code == 200, r.text

    data = {k: {"user_id": v["user_id"], "token": v["token"]} for k, v in out.items()}
    data["base_url"] = BASE_URL
    with open("/app/test_reports/ui_seed.json", "w") as fh:
        json.dump(data, fh, indent=2)
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
