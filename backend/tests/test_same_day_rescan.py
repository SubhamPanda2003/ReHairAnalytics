"""Characterization test: a second scan later on the SAME day.

Documents current behavior: create_tracking_session() no longer reuses a
same-day session (see services/sessions.py) -- every /scan call creates its
own session, timestamped precisely, so a user can capture multiple distinct,
independently viewable scans in one day instead of them silently merging.
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


def test_same_day_rescan_creates_separate_session():
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
    print("AFTER  session_id:", scan_session_id, "is a new session:", scan_session_id != SEED["patient"]["session_id"])
    print("AFTER  region:", a["region"], "per_region:", list(a["per_region"].keys()),
          "frames_analyzed:", a["frames_analyzed"], "frames_used:", a["frames_used"])

    # A same-day rescan must NOT reuse or merge into the earlier session --
    # it's its own independent scan.
    assert scan_session_id != SEED["patient"]["session_id"]
    assert isinstance(a["per_region"], dict) and a["per_region"]
    assert list(a["per_region"].keys()) == ["crown"], a["per_region"]
    assert a["frames_analyzed"] == 2, a["frames_analyzed"]

    # The earlier session's own analysis must be untouched by the later scan.
    still_before = s.get(f"{API}/sessions/{SEED['patient']['session_id']}", timeout=60).json()
    assert still_before["analysis"]["per_region"].keys() == before["analysis"]["per_region"].keys()
