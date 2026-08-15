"""Iteration-2 backend tests for the new feature batch:
POST /api/scan (multi-frame parallel analyze + top-N confidence averaging),
same-day session reuse, region focus, profile reminder, progress date labels,
GET /api/sessions/{id} best-image fields (side-by-side), existing manual flow.

Uses its OWN fresh seeded user (fixture `fresh_user`) so it is isolated from
test_backend.py's TestReHairEndToEnd which ends by deleting the account.
"""
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

from conftest import wait_for_analysis

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

FIX_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture(scope="class")
def fresh_user():
    """Fresh isolated user + session_token for scan tests."""
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    stamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    user_id = f"test-user-scan-{stamp}-{uuid.uuid4().hex[:6]}"
    token = f"test_session_scan_{stamp}_{uuid.uuid4().hex[:6]}"
    db.users.insert_one({
        "user_id": user_id,
        "email": f"qa+scan+{stamp}@example.com",
        "name": "Scan QA",
        "picture": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    yield user_id, token
    # cleanup
    for c in ("users", "user_sessions", "profiles", "tracking_sessions", "images", "analysis"):
        db[c].delete_many({"user_id": user_id})
    client.close()


@pytest.fixture(scope="class")
def sc(fresh_user):
    _, token = fresh_user
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def _read(name: str) -> bytes:
    with open(os.path.join(FIX_DIR, name), "rb") as fh:
        return fh.read()


class TestNewFeatures:
    """Class-scoped so state (session_id) flows between numbered tests."""

    # ---------- 1) /scan multi-frame + top-N averaging ----------
    def test_01_scan_creates_today_session_and_analyzes(self, sc):
        frames = [
            ("files", (f"frame_{i}.jpg", _read(f"scan_frame_{i}.jpg"), "image/jpeg"))
            for i in range(6)
        ]
        r = sc.post(f"{API}/scan", files=frames, data={"region": "full"}, timeout=240)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "session_id" in body
        session_id = body["session_id"]
        detail = wait_for_analysis(sc, API, session_id)
        a = detail["analysis"]
        # metric ranges
        for k in ("density_score", "coverage_score", "hairline_score", "overall_score",
                  "confidence", "quality_score"):
            assert 0 <= a[k] <= 100, f"{k}={a[k]}"
        assert a["region"] == "full"
        # NEW: all non-blurry frames are averaged (quality >= 40 kept)
        assert a["frames_analyzed"] == 6, f"frames_analyzed={a['frames_analyzed']}"
        assert a["frames_used"] == a["frames_analyzed"], (
            f"expected all sharp fixture frames to be used, "
            f"used={a['frames_used']} of {a['frames_analyzed']}")
        assert isinstance(a.get("ai_summary"), str) and len(a["ai_summary"]) > 20
        # baseline scan: no previous
        assert detail.get("previous_analysis") is None
        print(f"scan#1 sid={session_id} density={a['density_score']} "
              f"coverage={a['coverage_score']} hairline={a['hairline_score']} "
              f"overall={a['overall_score']} conf={a['confidence']} "
              f"summary_len={len(a['ai_summary'])}")
        type(self).session_id = session_id
        type(self).first_scores = (a["density_score"], a["coverage_score"], a["hairline_score"])

    # ---------- 2) Same-day reuse: second /scan reuses SAME session ----------
    def test_02_same_day_scan_reuses_session(self, sc):
        frames = [
            ("files", (f"f_{i}.jpg", _read(f"scan_frame_{i}.jpg"), "image/jpeg"))
            for i in (0, 2, 4)  # 3 new frames on same day
        ]
        r = sc.post(f"{API}/scan", files=frames, data={"region": "full"}, timeout=240)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["session_id"] == self.session_id, "should reuse today's session"
        a = wait_for_analysis(sc, API, body["session_id"])["analysis"]
        # 6 previous frames + 3 new = 9
        assert a["frames_analyzed"] == 9, f"frames_analyzed={a['frames_analyzed']}"
        assert a["frames_used"] == a["frames_analyzed"], f"frames_used={a['frames_used']}"
        print(f"scan#2 same session, frames_analyzed={a['frames_analyzed']}, "
              f"frames_used={a['frames_used']}")

    # ---------- 3) Region focus (crown) ----------
    def test_03_region_crown_persists(self, sc):
        frames = [("files", ("c.jpg", _read("scan_frame_1.jpg"), "image/jpeg")),
                  ("files", ("c2.jpg", _read("scan_frame_3.jpg"), "image/jpeg"))]
        r = sc.post(f"{API}/scan", files=frames, data={"region": "crown"}, timeout=240)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["session_id"] == self.session_id
        detail = wait_for_analysis(sc, API, body["session_id"])
        assert detail["analysis"]["region"] == "crown"
        # verify session doc reflects region
        rs = sc.get(f"{API}/sessions/{self.session_id}")
        assert rs.status_code == 200
        assert rs.json().get("region") == "crown"

    # ---------- 4) Invalid region falls back to 'full' ----------
    def test_04_invalid_region_falls_back(self, sc):
        frames = [("files", ("z.jpg", _read("scan_frame_0.jpg"), "image/jpeg"))]
        r = sc.post(f"{API}/scan", files=frames, data={"region": "invalid_zone"}, timeout=180)
        assert r.status_code == 200, r.text
        detail = wait_for_analysis(sc, API, r.json()["session_id"])
        assert detail["analysis"]["region"] == "full"

    # ---------- 5) Empty payload -> 400 ----------
    def test_05_scan_no_files_rejects(self, sc):
        # Send a non-image bytes file -> should be filtered, resulting in 400 "No valid frames"
        r = sc.post(f"{API}/scan",
                    files=[("files", ("bad.jpg", b"not-an-image", "image/jpeg"))],
                    data={"region": "full"}, timeout=60)
        assert r.status_code == 400, r.text

    # ---------- 6) Profile reminder round-trip ----------
    def test_06_profile_reminder_persists(self, sc):
        r = sc.post(f"{API}/profile", json={"reminder_enabled": True, "reminder_day": "Monday"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["reminder_enabled"] is True
        assert data["reminder_day"] == "Monday"

        r2 = sc.get(f"{API}/auth/me")
        assert r2.status_code == 200
        prof = r2.json().get("profile") or {}
        assert prof.get("reminder_enabled") is True
        assert prof.get("reminder_day") == "Monday"

    # ---------- 7) /progress returns last_date, days_since_last, and short-date labels ----------
    def test_07_progress_dates(self, sc):
        r = sc.get(f"{API}/progress")
        assert r.status_code == 200, r.text
        p = r.json()
        assert "last_date" in p and p["last_date"] is not None
        assert "days_since_last" in p and p["days_since_last"] is not None
        assert p["days_since_last"] >= 0
        pts = p.get("points") or []
        assert len(pts) >= 1
        # label like "Aug 08" (3-letter month + space + 2 digits)
        import re
        for pt in pts:
            assert "label" in pt
            assert re.match(r"^[A-Z][a-z]{2} \d{2}$", pt["label"]), f"bad label {pt['label']}"

    # ---------- 8) GET /sessions/{id} returns best-image fields ----------
    def test_08_session_best_image_fields(self, sc):
        r = sc.get(f"{API}/sessions/{self.session_id}")
        assert r.status_code == 200
        s = r.json()
        # 8 stored frames (6 + 3 same-day + 2 crown + 1 fallback) = 12; storage_path present
        assert s.get("current_best_image"), "current_best_image missing"
        assert s["current_best_image"].startswith("rehairanalytics/uploads/")
        # baseline == current here (single session), so baseline_best_image is None
        assert s["baseline_best_image"] is None
        assert s["baseline_analysis"] is None
        # previous is None for baseline session
        assert s["previous_analysis"] is None
        assert s["previous_best_image"] is None
        assert "analysis" in s and s["analysis"] is not None
        # each stored image has region
        imgs = s.get("images") or []
        assert len(imgs) >= 8
        assert all("region" in i for i in imgs)

    # ---------- 9) Manual flow still works: POST /sessions today reuses, upload+analyze ----------
    def test_09_manual_upload_still_works(self, sc):
        # POST /sessions on same day should return SAME session
        r = sc.post(f"{API}/sessions", json={"notes": "manual"})
        assert r.status_code == 200
        assert r.json()["id"] == self.session_id

        # Upload one manual view (real photo)
        files = {"file": ("front.jpg", _read("scalp_front.jpg"), "image/jpeg")}
        u = sc.post(f"{API}/sessions/{self.session_id}/upload",
                    files=files, data={"view": "front"}, timeout=180)
        assert u.status_code == 200, u.text
        udata = u.json()
        assert isinstance(udata.get("quality_score"), int)
        if udata.get("rejected"):
            pytest.skip(f"AI quality={udata['quality_score']} rejected upload; that's OK, response shape validated")
        assert udata["view"] == "front"
        assert udata["storage_path"].startswith("rehairanalytics/uploads/")

        # analyze again (uses this manual image)
        an = sc.post(f"{API}/sessions/{self.session_id}/analyze", timeout=180)
        assert an.status_code == 200, an.text
        a = an.json()["analysis"]
        for k in ("density_score", "coverage_score", "hairline_score", "overall_score"):
            assert 0 <= a[k] <= 100

    # ---------- 10) /api/files download for best image (auth required) ----------
    def test_10_download_best_image(self, sc):
        rs = sc.get(f"{API}/sessions/{self.session_id}")
        assert rs.status_code == 200
        path = rs.json().get("current_best_image")
        assert path
        # unauth
        r_un = requests.get(f"{API}/files/{path}")
        assert r_un.status_code == 401
        # authed
        r = sc.get(f"{API}/files/{path}", timeout=60)
        assert r.status_code == 200
        assert r.headers.get("Content-Type", "").startswith("image/")
        assert len(r.content) > 500
