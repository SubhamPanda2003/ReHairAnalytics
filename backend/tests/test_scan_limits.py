"""Scan-credit quota: per-user report counts, admin/super_admin-adjustable
limits (both roles, unlike role management which is super_admin-only), the
configurable global default + exhausted-message/whatsapp_number, and
enforcement on POST /scan.

Seeds isolated users directly in MongoDB (test_database) and authenticates
with Bearer <session_token>, same convention as test_roles_consults.py.
"""
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
SUPER_ADMIN_EMAIL = "iampandasubham@gmail.com"

FIXTURE_IMG = os.path.join(os.path.dirname(__file__), "fixtures", "scan_frame_0.jpg")


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


def _seed(db, label, email=None, role=None):
    stamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    uid = f"TEST_{label}-{stamp}-{uuid.uuid4().hex[:6]}"
    token = f"test_session_{label}_{stamp}_{uuid.uuid4().hex[:6]}"
    doc = {
        "user_id": uid,
        "email": email or f"TEST_qa+{label}+{stamp}@example.com",
        "name": f"TEST {label}",
        "picture": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if role:
        doc["role"] = role
    db.users.insert_one(doc)
    db.user_sessions.insert_one({
        "user_id": uid,
        "session_token": token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return uid, token, s


def _seed_scans(db, user_id, count):
    db.tracking_sessions.insert_many([
        {
            "id": f"TEST_session_{user_id}_{i}",
            "user_id": user_id,
            "date": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        for i in range(count)
    ])


@pytest.fixture(scope="module")
def actors(db):
    """super_admin (by email), plain admin, two plain users."""
    db.app_settings.delete_many({"key": "global"})  # clean slate for global defaults
    created = []
    sa = _seed(db, "scansuperadmin", email=SUPER_ADMIN_EMAIL)
    adm = _seed(db, "scanadmin", role="admin")
    user_a = _seed(db, "scanusera")
    user_b = _seed(db, "scanuserb")
    created += [sa[0], adm[0], user_a[0], user_b[0]]
    yield {"sa": sa, "admin": adm, "user_a": user_a, "user_b": user_b}
    for uid in created:
        db.users.delete_many({"user_id": uid})
        db.user_sessions.delete_many({"user_id": uid})
        db.tracking_sessions.delete_many({"user_id": uid})
    db.app_settings.delete_many({"key": "global"})


# --------------------------------------------------------------- RBAC gates
class TestScanUsageRBAC:
    def test_plain_user_forbidden(self, actors):
        c = actors["user_a"][2]
        assert c.get(f"{API}/admin/scan-usage").status_code == 403
        assert c.get(f"{API}/admin/settings").status_code == 403
        assert c.post(f"{API}/admin/settings", json={}).status_code == 403
        assert c.post(f"{API}/admin/users/{actors['user_b'][0]}/scan-limit", json={"scan_limit": 1}).status_code == 403

    def test_admin_and_super_admin_allowed(self, actors):
        for key in ("admin", "sa"):
            c = actors[key][2]
            assert c.get(f"{API}/admin/scan-usage").status_code == 200, key
            assert c.get(f"{API}/admin/settings").status_code == 200, key

    def test_unauthenticated_403(self):
        assert requests.get(f"{API}/admin/scan-usage").status_code == 401
        assert requests.get(f"{API}/admin/settings").status_code == 401


# -------------------------------------------------------------- quota basics
class TestQuotaDefaults:
    def test_unlimited_by_default(self, actors):
        r = actors["user_a"][2].get(f"{API}/scan/quota")
        assert r.status_code == 200, r.text
        q = r.json()
        assert q["limit"] is None
        assert q["remaining"] is None
        assert q["used"] == 0

    def test_privileged_roles_never_limited(self, actors, db):
        # Even if a scan_limit somehow ends up on an admin/super_admin doc,
        # quota stays unlimited -- only plain "user" accounts are gated.
        db.users.update_one({"user_id": actors["admin"][0]}, {"$set": {"scan_limit": 0}})
        r = actors["admin"][2].get(f"{API}/scan/quota")
        assert r.status_code == 200, r.text
        assert r.json()["limit"] is None
        db.users.update_one({"user_id": actors["admin"][0]}, {"$unset": {"scan_limit": ""}})


# ------------------------------------------------------- per-user overrides
class TestScanLimitManagement:
    def test_unknown_target_404(self, actors):
        r = actors["admin"][2].post(f"{API}/admin/users/no-such-uid/scan-limit", json={"scan_limit": 3})
        assert r.status_code == 404, r.text

    def test_negative_limit_400(self, actors):
        r = actors["admin"][2].post(f"{API}/admin/users/{actors['user_a'][0]}/scan-limit", json={"scan_limit": -1})
        assert r.status_code == 400, r.text

    def test_set_then_clear_override(self, actors):
        uid = actors["user_a"][0]
        r = actors["admin"][2].post(f"{API}/admin/users/{uid}/scan-limit", json={"scan_limit": 2})
        assert r.status_code == 200, r.text
        assert r.json()["effective_limit"] == 2

        rows = actors["sa"][2].get(f"{API}/admin/scan-usage").json()
        row = next(x for x in rows if x["user_id"] == uid)
        assert row["scan_limit"] == 2 and row["effective_limit"] == 2

        q = actors["user_a"][2].get(f"{API}/scan/quota").json()
        assert q["limit"] == 2 and q["remaining"] == 2

        # clear override -> back to unlimited (no global default set)
        r2 = actors["admin"][2].post(f"{API}/admin/users/{uid}/scan-limit", json={"scan_limit": None})
        assert r2.status_code == 200, r2.text
        assert r2.json()["effective_limit"] is None
        assert actors["user_a"][2].get(f"{API}/scan/quota").json()["limit"] is None

    def test_global_default_applies_without_override_only(self, actors):
        uid_a, uid_b = actors["user_a"][0], actors["user_b"][0]
        # user_b gets an explicit override; user_a stays on the global default
        assert actors["admin"][2].post(f"{API}/admin/users/{uid_b}/scan-limit", json={"scan_limit": 9}).status_code == 200

        r = actors["sa"][2].post(f"{API}/admin/settings", json={"default_scan_limit": 4})
        assert r.status_code == 200, r.text
        assert r.json()["default_scan_limit"] == 4

        assert actors["user_a"][2].get(f"{API}/scan/quota").json()["limit"] == 4
        assert actors["user_b"][2].get(f"{API}/scan/quota").json()["limit"] == 9

        # reset for later tests
        assert actors["sa"][2].post(f"{API}/admin/settings", json={"default_scan_limit": None}).status_code == 200
        assert actors["admin"][2].post(f"{API}/admin/users/{uid_b}/scan-limit", json={"scan_limit": None}).status_code == 200


# ---------------------------------------------------------- enforcement + message
class TestScanEnforcement:
    def test_blocked_once_used_reaches_limit(self, actors, db):
        uid = actors["user_b"][0]
        _seed_scans(db, uid, 2)
        assert actors["admin"][2].post(f"{API}/admin/users/{uid}/scan-limit", json={"scan_limit": 2}).status_code == 200

        q = actors["user_b"][2].get(f"{API}/scan/quota").json()
        assert q["used"] == 2 and q["remaining"] == 0

        settings = actors["sa"][2].post(f"{API}/admin/settings", json={
            "exhausted_message": "TEST out of credits",
            "whatsapp_number": "+91 6281482850",
        }).json()

        with open(FIXTURE_IMG, "rb") as f:
            r = actors["user_b"][2].post(
                f"{API}/scan",
                files=[("files", ("frame.jpg", f, "image/jpeg"))],
                data={"region": "full", "frame_regions": ["front"], "precision": "false"},
            )
        assert r.status_code == 403, r.text
        detail = r.json()["detail"]
        assert detail["code"] == "scan_limit_reached"
        assert detail["message"] == settings["exhausted_message"]
        assert detail["whatsapp_number"] == settings["whatsapp_number"]

        # no session was created for the blocked attempt
        assert db.tracking_sessions.count_documents({"user_id": uid}) == 2

        db.app_settings.delete_many({"key": "global"})
        assert actors["admin"][2].post(f"{API}/admin/users/{uid}/scan-limit", json={"scan_limit": None}).status_code == 200


# ------------------------------------------------------ precision cost model
class TestPrecisionCreditCost:
    """Precision scans cost PRECISION_SCAN_CREDIT_COST credits, normal scans
    cost SCAN_CREDIT_COST (see services.quota). Own isolated user rather than
    actors['user_a']/['user_b'] -- other classes in this module mutate those
    and leave scan history behind on them."""

    @pytest.fixture(scope="class")
    def own_user(self, db):
        uid, _, c = _seed(db, "precisioncost")
        yield uid, c
        db.users.delete_many({"user_id": uid})
        db.user_sessions.delete_many({"user_id": uid})
        db.tracking_sessions.delete_many({"user_id": uid})

    def test_01_normal_scan_costs_one_credit(self, own_user, db):
        uid, c = own_user
        with open(FIXTURE_IMG, "rb") as f:
            r = c.post(f"{API}/scan", files=[("files", ("frame.jpg", f, "image/jpeg"))],
                       data={"region": "full", "frame_regions": ["front"], "precision": "false"})
        assert r.status_code == 200, r.text
        sess = db.tracking_sessions.find_one({"id": r.json()["session_id"]}, {"_id": 0})
        assert sess["credits_used"] == 1, sess
        assert sess["precision"] is False, sess

    def test_02_precision_scan_costs_three_credits(self, own_user, db):
        uid, c = own_user
        with open(FIXTURE_IMG, "rb") as f:
            r = c.post(f"{API}/scan", files=[("files", ("frame.jpg", f, "image/jpeg"))],
                       data={"region": "full", "frame_regions": ["front"], "precision": "true"})
        assert r.status_code == 200, r.text
        sess = db.tracking_sessions.find_one({"id": r.json()["session_id"]}, {"_id": 0})
        assert sess["credits_used"] == 3, sess
        assert sess["precision"] is True, sess

    def test_03_quota_reports_credits_not_raw_scan_count(self, own_user):
        _, c = own_user
        q = c.get(f"{API}/scan/quota").json()
        assert q["scan_count"] == 2, q  # 2 scans...
        assert q["used"] == 4, q        # ...but 4 credits (1 normal + 1 precision)
        assert q["scan_cost"] == 1
        assert q["precision_scan_cost"] == 3

    def test_04_admin_view_shows_both_numbers(self, actors, own_user):
        uid, _ = own_user
        rows = actors["admin"][2].get(f"{API}/admin/scan-usage").json()
        row = next(x for x in rows if x["user_id"] == uid)
        assert row["scan_count"] == 2, row
        assert row["credits_used"] == 4, row

    def test_05_precision_blocked_when_only_enough_for_normal(self, own_user, actors):
        uid, c = own_user
        # 4 credits used so far; cap the limit at 5 -- 1 remains, enough for
        # a normal scan but not a precision one.
        assert actors["admin"][2].post(f"{API}/admin/users/{uid}/scan-limit", json={"scan_limit": 5}).status_code == 200
        assert c.get(f"{API}/scan/quota").json()["remaining"] == 1

        with open(FIXTURE_IMG, "rb") as f:
            r_precision = c.post(f"{API}/scan", files=[("files", ("frame.jpg", f, "image/jpeg"))],
                                  data={"region": "full", "frame_regions": ["front"], "precision": "true"})
        assert r_precision.status_code == 403, r_precision.text
        assert r_precision.json()["detail"]["code"] == "scan_limit_reached"

        # a normal (1-credit) scan still fits in the 1 remaining credit
        with open(FIXTURE_IMG, "rb") as f:
            r_normal = c.post(f"{API}/scan", files=[("files", ("frame.jpg", f, "image/jpeg"))],
                               data={"region": "full", "frame_regions": ["front"], "precision": "false"})
        assert r_normal.status_code == 200, r_normal.text
        assert c.get(f"{API}/scan/quota").json()["remaining"] == 0

    def test_06_missing_credits_used_field_defaults_to_one(self, own_user, db):
        # Legacy/pre-migration sessions with no credits_used field at all
        # must still count as SCAN_CREDIT_COST, not 0.
        uid, c = own_user
        before = c.get(f"{API}/scan/quota").json()["used"]
        db.tracking_sessions.insert_one({
            "id": f"TEST_legacy_{uid}", "user_id": uid,
            "date": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            # deliberately no credits_used field
        })
        after = c.get(f"{API}/scan/quota").json()["used"]
        assert after == before + 1, (before, after)
