"""Iteration-6 deployment-fix verification tests.

Focus:
- GET /health (no /api prefix) is the k8s probe path (was 404) -> must return 200 {"status":"healthy"}
- GET /api/health and GET /api/ still healthy
- /api/sessions and /api/timeline: batched _attach_children returns images list and analysis object/null
- POST /api/scan (2-3 real JPEGs) end-to-end with thread-offloaded storage + image ops
- GET /api/files/{path} serves stored bytes via asyncio.to_thread(get_object)
- Event-loop responsiveness: while /api/scan is in flight, /health responds in <2s
"""
import os
import time
import uuid
import threading
import concurrent.futures
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

PUBLIC_BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PUBLIC_API = f"{PUBLIC_BASE}/api"
# The k8s probe hits the backend pod directly on 8001, not via the ingress
# (the ingress only routes /api to the backend). We validate the probe path
# against the actual backend service exposed on localhost.
LOCAL_BASE = "http://localhost:8001"
LOCAL_API = f"{LOCAL_BASE}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
FIX_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture(scope="class")
def deploy_user():
    """Fresh isolated user + session_token for deploy tests."""
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    stamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    user_id = f"test-user-deploy-{stamp}-{uuid.uuid4().hex[:6]}"
    token = f"test_session_deploy_{stamp}_{uuid.uuid4().hex[:6]}"
    db.users.insert_one({
        "user_id": user_id,
        "email": f"qa+deploy+{stamp}@example.com",
        "name": "Deploy QA",
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
    for c in ("users", "user_sessions", "profiles", "tracking_sessions", "images", "analysis"):
        db[c].delete_many({"user_id": user_id})
    client.close()


@pytest.fixture(scope="class")
def dc(deploy_user):
    _, token = deploy_user
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def _read(name: str) -> bytes:
    with open(os.path.join(FIX_DIR, name), "rb") as fh:
        return fh.read()


class TestDeployFix:
    """Iteration-6: /health probe + event-loop offloading + batched sessions/timeline."""

    # ---------- health endpoints ----------
    def test_01_health_no_api_prefix_backend(self):
        """This is THE deploy fix: the k8s probe path GET /health directly on 8001."""
        r = requests.get(f"{LOCAL_BASE}/health", timeout=5)
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:200]}"
        j = r.json()
        assert j == {"status": "healthy"}, f"unexpected body: {j}"

    def test_02_api_health_backend(self):
        r = requests.get(f"{LOCAL_API}/health", timeout=5)
        assert r.status_code == 200
        assert r.json() == {"status": "healthy"}

    def test_03_api_health_public(self):
        """/api/health via public ingress should also be healthy (no auth)."""
        r = requests.get(f"{PUBLIC_API}/health", timeout=10)
        assert r.status_code == 200, r.text[:200]
        assert r.json() == {"status": "healthy"}

    def test_04_api_root_public(self):
        r = requests.get(f"{PUBLIC_API}/", timeout=10)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body.get("status") == "ok"
        assert "message" in body

    def test_05_health_no_auth_required(self):
        """/health and /api/health should not require auth."""
        r1 = requests.get(f"{LOCAL_BASE}/health", timeout=5)
        r2 = requests.get(f"{LOCAL_API}/health", timeout=5)
        assert r1.status_code == 200 and r2.status_code == 200

    # ---------- /api/scan end-to-end with 2-3 real JPEGs ----------
    def test_06_scan_end_to_end(self, dc):
        """Real /api/scan with 3 frames: storage + AI + thread offloading."""
        frames = [
            ("files", (f"f_{i}.jpg", _read(f"scan_frame_{i}.jpg"), "image/jpeg"))
            for i in range(3)
        ]
        r = dc.post(f"{PUBLIC_API}/scan", files=frames, data={"region": "full"}, timeout=240)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "session_id" in body and "analysis" in body
        a = body["analysis"]
        for k in ("density_score", "coverage_score", "hairline_score", "overall_score",
                  "confidence", "quality_score"):
            assert 0 <= a[k] <= 100, f"{k}={a[k]}"
        assert isinstance(a.get("ai_summary"), str) and len(a["ai_summary"]) > 20
        assert a["region"] == "full"
        assert a["frames_analyzed"] == 3
        type(self).session_id = body["session_id"]
        print(f"scan sid={body['session_id']} density={a['density_score']} "
              f"coverage={a['coverage_score']} hairline={a['hairline_score']} "
              f"overall={a['overall_score']} summary_len={len(a['ai_summary'])}")

    # ---------- batched _attach_children on /api/sessions ----------
    def test_07_sessions_batched_shape(self, dc):
        r = dc.get(f"{PUBLIC_API}/sessions", timeout=30)
        assert r.status_code == 200, r.text
        arr = r.json()
        assert isinstance(arr, list) and len(arr) >= 1
        # find our just-created session
        sess = next((s for s in arr if s["id"] == self.session_id), None)
        assert sess is not None, "created session missing from /api/sessions"
        # batched fields
        assert "images" in sess and isinstance(sess["images"], list)
        assert len(sess["images"]) == 3, f"expected 3 stored images, got {len(sess['images'])}"
        for im in sess["images"]:
            assert im["tracking_session_id"] == self.session_id, (
                "attached image belongs to wrong session -> batching bug"
            )
            assert "storage_path" in im and im["storage_path"].startswith("rehairanalytics/uploads/")
        assert "analysis" in sess and sess["analysis"] is not None
        assert sess["analysis"]["tracking_session_id"] == self.session_id, (
            "attached analysis belongs to wrong session -> batching bug"
        )
        type(self).storage_path = sess["images"][0]["storage_path"]

    # ---------- batched _attach_children on /api/timeline ----------
    def test_08_timeline_batched_shape(self, dc):
        r = dc.get(f"{PUBLIC_API}/timeline", timeout=30)
        assert r.status_code == 200, r.text
        arr = r.json()
        assert isinstance(arr, list) and len(arr) >= 1
        sess = next((s for s in arr if s["id"] == self.session_id), None)
        assert sess is not None
        assert isinstance(sess["images"], list) and len(sess["images"]) == 3
        assert all(im["tracking_session_id"] == self.session_id for im in sess["images"])
        assert sess["analysis"] is not None
        assert sess["analysis"]["tracking_session_id"] == self.session_id

    # ---------- /api/files thread-offloaded get_object ----------
    def test_09_files_download(self, dc):
        assert getattr(self, "storage_path", None), "no storage_path from previous test"
        r = dc.get(f"{PUBLIC_API}/files/{self.storage_path}", timeout=60)
        assert r.status_code == 200, r.text[:200]
        assert r.headers.get("Content-Type", "").startswith("image/")
        assert len(r.content) > 500, f"file too small: {len(r.content)} bytes"

    def test_10_files_requires_auth(self):
        r = requests.get(f"{PUBLIC_API}/files/rehairanalytics/uploads/x/y.jpg", timeout=10)
        assert r.status_code == 401

    # ---------- event-loop responsiveness ----------
    def test_11_health_fast_during_scan(self, dc):
        """While /api/scan is in flight (2 frames), poll /health locally.
        Each poll must return 200 in <2s -> the event loop is not blocked
        by the sync store.put_object / Pillow work (they are now to_thread'd)."""
        frames = [
            ("files", (f"g_{i}.jpg", _read(f"scan_frame_{i}.jpg"), "image/jpeg"))
            for i in range(2)
        ]

        def do_scan():
            return dc.post(f"{PUBLIC_API}/scan", files=frames, data={"region": "full"}, timeout=240)

        results = []  # list of (elapsed_s, status_code)
        stop = threading.Event()

        def poll_health():
            while not stop.is_set():
                t0 = time.monotonic()
                try:
                    hr = requests.get(f"{LOCAL_BASE}/health", timeout=5)
                    dt = time.monotonic() - t0
                    results.append((dt, hr.status_code))
                except Exception as e:
                    results.append((time.monotonic() - t0, f"err:{e}"))
                time.sleep(0.3)

        poller = threading.Thread(target=poll_health, daemon=True)
        poller.start()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(do_scan)
            scan_resp = fut.result()
        stop.set()
        poller.join(timeout=2)

        assert scan_resp.status_code == 200, scan_resp.text[:300]
        assert len(results) >= 3, f"too few /health polls captured: {len(results)}"
        slow = [(dt, sc) for dt, sc in results if not (isinstance(sc, int) and sc == 200 and dt < 2.0)]
        print(f"/health polls during scan: total={len(results)} slow_or_err={len(slow)} "
              f"max_dt={max(dt for dt, _ in results):.3f}s")
        assert not slow, f"event-loop blocked: {slow[:5]}"
