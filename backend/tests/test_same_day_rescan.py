"""Characterization test: same-day second scan with a different region.

Documents how finalize_day_analysis behaves when a user scans 'full' (multi-region)
and then re-scans 'crown' on the SAME day (get_or_create_today_session reuses the
session, so all frames accumulate).
"""
import json
import os
from pathlib import Path

import requests

from conftest import wait_for_analysis

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
FIX = Path("/app/backend/tests/fixtures")
SEED = json.loads(Path("/app/test_reports/region_ui_seed.json").read_text())


def test_same_day_rescan_accumulates_regions():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {SEED['patient']['token']}"})
    before = s.get(f"{API}/sessions/{SEED['patient']['session_id']}", timeout=60).json()
    print("BEFORE per_region:", list(before["analysis"]["per_region"].keys()),
          "region:", before["analysis"]["region"],
          "frames_analyzed:", before["analysis"]["frames_analyzed"])

    files = [("files", (f"scan_frame_{i}.jpg", (FIX / f"scan_frame_{i}.jpg").read_bytes(), "image/jpeg"))
             for i in (0, 1)]
    data = [("region", "crown"), ("frame_regions", "crown"), ("frame_regions", "crown")]
    r = s.post(f"{API}/scan", data=data, files=files, timeout=300)
    assert r.status_code == 200, r.text[:500]
    scan_session_id = r.json()["session_id"]
    detail = wait_for_analysis(s, API, scan_session_id)
    a = detail["analysis"]
    print("AFTER  session_id same:", scan_session_id == SEED["patient"]["session_id"])
    print("AFTER  region:", a["region"], "per_region:", list(a["per_region"].keys()),
          "frames_analyzed:", a["frames_analyzed"], "frames_used:", a["frames_used"])
    # No crash / valid payload regardless of the design decision.
    assert isinstance(a["per_region"], dict) and a["per_region"]
