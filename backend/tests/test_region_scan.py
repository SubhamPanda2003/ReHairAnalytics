"""Iteration-7 tests: per-region multi-frame /api/scan (repeated frame_regions form field).

Covers:
  - POST /api/scan region=full with repeated frame_regions -> per_region breakdown
  - POST /api/scan region=crown with all-crown frame_regions -> single per_region entry
  - repeated frame_regions parses as list (no 422)
  - GET /api/sessions/{id} + /api/timeline expose analysis.per_region
"""
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import requests
from pymongo import MongoClient

from conftest import wait_for_analysis

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
FIX = Path("/app/backend/tests/fixtures")
# hairline_score is intentionally excluded here: a frontal hairline isn't visible
# from the crown or the back of the head, so it's only present for regions where
# it actually is (see ai_service.HAIRLINE_VISIBLE_REGIONS) -- checked separately below.
METRIC_KEYS = ["density_score", "coverage_score", "overall_score",
               "confidence", "quality_score", "visible_scalp_pct", "hair_coverage_pct"]
HAIRLINE_VISIBLE_REGIONS = {"full", "front", "hairline", "left", "right"}


def _db():
    return MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
        os.environ.get("DB_NAME", "test_database")]


def _seed(db, label):
    stamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    uid = f"TEST_region-{label}-{stamp}-{uuid.uuid4().hex[:6]}"
    tok = f"test_session_region_{label}_{stamp}_{uuid.uuid4().hex[:6]}"
    db.users.insert_one({"user_id": uid, "email": f"TEST_region+{label}+{stamp}@example.com",
                         "name": f"TEST {label}", "picture": "",
                         "created_at": datetime.now(timezone.utc).isoformat()})
    db.user_sessions.insert_one({"user_id": uid, "session_token": tok,
                                 "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                                 "created_at": datetime.now(timezone.utc).isoformat()})
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return uid, tok, s


def _purge(db, uid):
    for c in ("users", "user_sessions", "profiles", "tracking_sessions", "images", "analysis"):
        db[c].delete_many({"user_id": uid})


def _files(n):
    out = []
    for i in range(n):
        p = FIX / f"scan_frame_{i % 6}.jpg"
        out.append(("files", (p.name, p.read_bytes(), "image/jpeg")))
    return out


class TestFullRegionScan:
    """region=full with 6 distinct sub-region tags."""

    REGIONS = ["front", "left", "crown", "right", "hairline", "back"]

    @pytest.fixture(scope="class")
    def ctx(self):
        db = _db()
        uid, tok, s = _seed(db, "full")
        yield {"db": db, "uid": uid, "token": tok, "sess": s}
        _purge(db, uid)

    @pytest.fixture(scope="class")
    def scan_result(self, ctx):
        data = [("region", "full")] + [("frame_regions", r) for r in self.REGIONS]
        r = ctx["sess"].post(f"{API}/scan", data=data, files=_files(len(self.REGIONS)), timeout=300)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:800]}"
        session_id = r.json()["session_id"]
        detail = wait_for_analysis(ctx["sess"], API, session_id)
        return {"session_id": session_id, "analysis": detail["analysis"]}

    def test_no_422_repeated_frame_regions(self, scan_result):
        # scan_result fixture already asserted 200; explicit guard against the old
        # "Input should be a valid list" 422.
        assert "analysis" in scan_result

    def test_analysis_region_and_per_region(self, scan_result):
        a = scan_result["analysis"]
        assert a["region"] == "full"
        assert "_id" not in a
        pr = a.get("per_region")
        assert isinstance(pr, dict) and pr, f"per_region missing/empty: {pr}"
        assert set(pr.keys()).issubset(set(self.REGIONS)), pr.keys()
        # blurry frames (quality<40) may be dropped, but most should survive
        assert len(pr) >= 4, f"only {len(pr)} regions kept: {list(pr)}"
        assert a["frames_used"] == len(pr), (a["frames_used"], list(pr))
        for reg, m in pr.items():
            for k in METRIC_KEYS:
                assert k in m, f"{reg} missing {k}"
                assert isinstance(m[k], int) and 0 <= m[k] <= 100, (reg, k, m[k])
            # hairline is only meaningful (and only present) for regions where the
            # frontal hairline is actually in frame -- crown/back get no reading.
            if reg in HAIRLINE_VISIBLE_REGIONS:
                assert "hairline_score" in m and isinstance(m["hairline_score"], int) and 0 <= m["hairline_score"] <= 100, (reg, m)
            else:
                assert "hairline_score" not in m, f"{reg} should not have a hairline_score: {m}"

    def test_overall_blend_within_region_range(self, scan_result):
        a = scan_result["analysis"]
        pr = a["per_region"]
        for k in ("density_score", "coverage_score", "overall_score"):
            vals = [m[k] for m in pr.values()]
            assert min(vals) - 1 <= a[k] <= max(vals) + 1, (k, a[k], vals)
        # overall hairline_score should only ever be blended from the hairline-visible
        # regions actually captured (front/left/right/hairline here), never crown/back.
        hairline_vals = [m["hairline_score"] for reg, m in pr.items() if reg in HAIRLINE_VISIBLE_REGIONS]
        if hairline_vals:
            assert min(hairline_vals) - 1 <= a["hairline_score"] <= max(hairline_vals) + 1, (a["hairline_score"], hairline_vals)

    def test_one_best_frame_stored_per_region(self, ctx, scan_result):
        sid = scan_result["session_id"]
        imgs = list(ctx["db"].images.find({"tracking_session_id": sid}, {"_id": 0}))
        assert len(imgs) == len(self.REGIONS), len(imgs)
        tagged = [i["region"] for i in imgs]
        assert sorted(tagged) == sorted(self.REGIONS), tagged
        # for each per_region entry the metrics must equal the highest-confidence frame of that region
        for reg, m in scan_result["analysis"]["per_region"].items():
            cands = [i for i in imgs if i.get("region") == reg]
            best = max(cands, key=lambda x: x.get("confidence", 0))
            assert m["confidence"] == best["confidence"], (reg, m["confidence"], best["confidence"])
            assert m["density_score"] == best["density_score"], reg

    def test_session_detail_and_timeline_expose_per_region(self, ctx, scan_result):
        sid = scan_result["session_id"]
        r = ctx["sess"].get(f"{API}/sessions/{sid}", timeout=60)
        assert r.status_code == 200, r.text[:400]
        s = r.json()
        assert s["id"] == sid
        assert len(s.get("images", [])) == len(self.REGIONS)
        assert s["analysis"]["per_region"] == scan_result["analysis"]["per_region"]

        r = ctx["sess"].get(f"{API}/timeline", timeout=60)
        assert r.status_code == 200, r.text[:400]
        tl = r.json()
        rows = tl if isinstance(tl, list) else tl.get("sessions", tl.get("timeline", []))
        row = next((x for x in rows if x.get("id") == sid), None)
        assert row is not None, f"session {sid} not in timeline"
        assert row["analysis"]["per_region"], row["analysis"]
        assert len(row.get("images", [])) == len(self.REGIONS)


class TestSingleRegionScan:
    """region=crown, all frames tagged crown -> single per_region entry (averaged top frames)."""

    @pytest.fixture(scope="class")
    def ctx(self):
        db = _db()
        uid, tok, s = _seed(db, "crown")
        yield {"db": db, "uid": uid, "token": tok, "sess": s}
        _purge(db, uid)

    def test_crown_explicit_regions(self, ctx):
        n = 4
        data = [("region", "crown")] + [("frame_regions", "crown")] * n
        r = ctx["sess"].post(f"{API}/scan", data=data, files=_files(n), timeout=300)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:800]}"
        detail = wait_for_analysis(ctx["sess"], API, r.json()["session_id"])
        a = detail["analysis"]
        assert a["region"] == "crown"
        assert list(a["per_region"].keys()) == ["crown"], a["per_region"].keys()
        m = a["per_region"]["crown"]
        for k in METRIC_KEYS:
            assert 0 <= m[k] <= 100, (k, m[k])
        # crown has no frontal hairline in frame -- no hairline reading anywhere for this scan.
        assert "hairline_score" not in m, m
        assert a.get("hairline_score") is None, a["hairline_score"]
        assert a["frames_analyzed"] == n
        assert 1 <= a["frames_used"] <= n
        # overall metrics equal the single-region averages
        assert a["density_score"] == m["density_score"]
        assert a["overall_score"] == m["overall_score"]


class TestOmittedFrameRegions:
    """frame_regions omitted entirely -> falls back to overall region."""

    @pytest.fixture(scope="class")
    def ctx(self):
        db = _db()
        uid, tok, s = _seed(db, "noreg")
        yield {"db": db, "uid": uid, "token": tok, "sess": s}
        _purge(db, uid)

    def test_hairline_without_frame_regions(self, ctx):
        r = ctx["sess"].post(f"{API}/scan", data={"region": "hairline"}, files=_files(2), timeout=300)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:800]}"
        session_id = r.json()["session_id"]
        detail = wait_for_analysis(ctx["sess"], API, session_id)
        a = detail["analysis"]
        assert a["region"] == "hairline"
        assert list(a["per_region"].keys()) == ["hairline"], a["per_region"]
        imgs = list(ctx["db"].images.find({"tracking_session_id": session_id}, {"_id": 0}))
        assert all(i["region"] == "hairline" for i in imgs), [i["region"] for i in imgs]

    def test_scan_requires_auth(self):
        r = requests.post(f"{API}/scan", data={"region": "full"}, files=_files(1), timeout=60)
        assert r.status_code in (401, 403), r.status_code
