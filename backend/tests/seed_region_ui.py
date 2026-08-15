"""Seed a patient user with a real full multi-region scan + a super_admin user for UI tests.

Writes /app/test_reports/region_ui_seed.json
"""
import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from pymongo import MongoClient

from conftest import wait_for_analysis

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
FIX = Path("/app/backend/tests/fixtures")
db = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
    os.environ.get("DB_NAME", "test_database")]


def seed(label, email=None, role=None):
    stamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    uid = f"TEST_rui-{label}-{stamp}-{uuid.uuid4().hex[:6]}"
    tok = f"test_session_rui_{label}_{stamp}_{uuid.uuid4().hex[:6]}"
    doc = {"user_id": uid, "email": email or f"TEST_rui+{label}+{stamp}@example.com",
           "name": f"TEST {label}", "picture": "",
           "created_at": datetime.now(timezone.utc).isoformat()}
    if role:
        doc["role"] = role
    db.users.insert_one(doc)
    db.user_sessions.insert_one({"user_id": uid, "session_token": tok,
                                 "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                                 "created_at": datetime.now(timezone.utc).isoformat()})
    return uid, tok


def main():
    out = {"base_url": BASE}
    uid, tok = seed("patient")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    s.post(f"{API}/profile", json={"age": 32, "gender": "male", "hair_type": "straight",
                                   "concern": "thinning", "goal": "regrowth"}, timeout=60)
    regions = ["front", "left", "crown", "right", "hairline", "back"]
    files = [("files", (f"scan_frame_{i}.jpg", (FIX / f"scan_frame_{i}.jpg").read_bytes(), "image/jpeg"))
             for i in range(len(regions))]
    data = [("region", "full")] + [("frame_regions", r) for r in regions]
    r = s.post(f"{API}/scan", data=data, files=files, timeout=300)
    print("scan:", r.status_code)
    sid = r.json()["session_id"] if r.status_code == 200 else None
    per_region = list(wait_for_analysis(s, API, sid)["analysis"]["per_region"].keys()) if sid else {}
    out["patient"] = {"user_id": uid, "token": tok, "session_id": sid, "per_region": per_region}

    auid, atok = seed("superadmin", email="iampandasubham@gmail.com")
    out["superadmin"] = {"user_id": auid, "token": atok}

    Path("/app/test_reports/region_ui_seed.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
