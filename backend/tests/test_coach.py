"""Hair-coach layer: admin-managed 1:1 pairing between a plain user and a
coach, opt-in report sharing, and the coach's read-only patient/report view.

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


@pytest.fixture(scope="module")
def actors(db):
    """super_admin (by email), plain admin, two plain users, two coaches."""
    created = []
    sa = _seed(db, "coachsuperadmin", email=SUPER_ADMIN_EMAIL)
    adm = _seed(db, "coachadmin", role="admin")
    user_a = _seed(db, "coachusera")
    user_b = _seed(db, "coachuserb")
    coach_a = _seed(db, "coacha", role="coach")
    coach_b = _seed(db, "coachb", role="coach")
    created += [sa[0], adm[0], user_a[0], user_b[0], coach_a[0], coach_b[0]]
    yield {"sa": sa, "admin": adm, "user_a": user_a, "user_b": user_b, "coach_a": coach_a, "coach_b": coach_b}
    for uid in created:
        db.users.delete_many({"user_id": uid})
        db.user_sessions.delete_many({"user_id": uid})


def _assign(client, target_uid, coach_uid):
    return client.post(f"{API}/admin/users/{target_uid}/coach", json={"coach_id": coach_uid})


# ------------------------------------------------------- role promotion
class TestCoachRolePromotion:
    def test_super_admin_can_promote_to_coach(self, db, actors):
        uid, _, c = _seed(db, "promocand")
        try:
            assert c.get(f"{API}/auth/me").json()["role"] == "user"
            r = actors["sa"][2].post(f"{API}/admin/users/{uid}/role", json={"role": "coach"})
            assert r.status_code == 200, r.text
            assert r.json()["role"] == "coach"
            assert c.get(f"{API}/auth/me").json()["role"] == "coach"
        finally:
            db.users.delete_many({"user_id": uid})
            db.user_sessions.delete_many({"user_id": uid})

    def test_admin_cannot_promote_to_coach(self, actors):
        target_uid = actors["user_a"][0]
        r = actors["admin"][2].post(f"{API}/admin/users/{target_uid}/role", json={"role": "coach"})
        assert r.status_code == 403, r.text

    def test_super_admin_rejects_unknown_role(self, actors):
        target_uid = actors["user_a"][0]
        r = actors["sa"][2].post(f"{API}/admin/users/{target_uid}/role", json={"role": "bogus"})
        assert r.status_code == 400, r.text


# -------------------------------------------------------- admin pairing
class TestCoachAssignment:
    def test_admin_can_assign_coach(self, actors):
        user_uid = actors["user_a"][0]
        coach_uid = actors["coach_a"][0]
        r = _assign(actors["admin"][2], user_uid, coach_uid)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["coach_id"] == coach_uid
        assert body["share_with_coach"] is False

    def test_assigning_unknown_coach_404(self, actors):
        r = _assign(actors["admin"][2], actors["user_a"][0], "TEST_not_a_real_coach")
        assert r.status_code == 404, r.text

    def test_assigning_to_unknown_user_404(self, actors):
        r = _assign(actors["admin"][2], "TEST_not_a_real_user", actors["coach_a"][0])
        assert r.status_code == 404, r.text

    def test_plain_user_forbidden_from_assigning(self, actors):
        r = _assign(actors["user_a"][2], actors["user_a"][0], actors["coach_a"][0])
        assert r.status_code == 403, r.text

    def test_admin_list_coaches_includes_both_excludes_users(self, actors):
        r = actors["admin"][2].get(f"{API}/admin/coaches")
        assert r.status_code == 200, r.text
        ids = {c["user_id"] for c in r.json()}
        assert actors["coach_a"][0] in ids
        assert actors["coach_b"][0] in ids
        assert actors["user_a"][0] not in ids

    def test_admin_coach_assignments_reflects_pairing(self, actors):
        user_uid = actors["user_a"][0]
        coach_uid = actors["coach_a"][0]
        _assign(actors["admin"][2], user_uid, coach_uid)
        r = actors["admin"][2].get(f"{API}/admin/coach-assignments")
        assert r.status_code == 200, r.text
        row = next(row for row in r.json() if row["user_id"] == user_uid)
        assert row["coach_id"] == coach_uid
        assert row["coach_name"] == actors["coach_a"][2].get(f"{API}/auth/me").json()["name"]


# ----------------------------------------------- reassignment resets share
class TestCoachReassignmentResetsSharing:
    def test_reassigning_coach_resets_share(self, actors):
        user_client = actors["user_b"][2]
        user_uid = actors["user_b"][0]
        _assign(actors["admin"][2], user_uid, actors["coach_a"][0])
        assert user_client.post(f"{API}/coach/share", json={"share": True}).status_code == 200
        assert user_client.get(f"{API}/coach/mine").json()["share_with_coach"] is True

        _assign(actors["admin"][2], user_uid, actors["coach_b"][0])
        mine = user_client.get(f"{API}/coach/mine").json()
        assert mine["coach"]["user_id"] == actors["coach_b"][0]
        assert mine["share_with_coach"] is False


# ----------------------------------------------------- sharing + coach view
class TestCoachSharingAndReport:
    @pytest.fixture(scope="class")
    def paired(self, db, actors):
        """Own isolated user+coach pair so this class doesn't fight over
        share_with_coach state with the other classes above."""
        user = _seed(db, "coachshareuser")
        coach = _seed(db, "coachshareCoach", role="coach")
        r = actors["sa"][2].post(f"{API}/admin/users/{user[0]}/coach", json={"coach_id": coach[0]})
        assert r.status_code == 200, r.text
        yield {"user": user, "coach": coach}
        for uid in (user[0], coach[0]):
            db.users.delete_many({"user_id": uid})
            db.user_sessions.delete_many({"user_id": uid})

    def test_01_report_403_before_sharing(self, paired):
        user_uid, coach_client = paired["user"][0], paired["coach"][2]
        r = coach_client.get(f"{API}/coach/patients/{user_uid}/report")
        assert r.status_code == 403, r.text

    def test_02_unshared_patient_not_listed(self, paired):
        coach_client = paired["coach"][2]
        r = coach_client.get(f"{API}/coach/patients")
        assert r.status_code == 200, r.text
        assert paired["user"][0] not in {p["user_id"] for p in r.json()}

    def test_03_share_then_visible_to_coach(self, paired):
        user_client, user_uid, coach_client = paired["user"][2], paired["user"][0], paired["coach"][2]
        r = user_client.post(f"{API}/coach/share", json={"share": True})
        assert r.status_code == 200 and r.json()["share_with_coach"] is True

        listed = coach_client.get(f"{API}/coach/patients").json()
        assert user_uid in {p["user_id"] for p in listed}

        rep = coach_client.get(f"{API}/coach/patients/{user_uid}/report")
        assert rep.status_code == 200, rep.text
        body = rep.json()
        assert "progress" in body and "recent_photos" in body

    def test_04_unshare_revokes_immediately(self, paired):
        user_client, user_uid, coach_client = paired["user"][2], paired["user"][0], paired["coach"][2]
        assert user_client.post(f"{API}/coach/share", json={"share": False}).status_code == 200
        assert coach_client.get(f"{API}/coach/patients/{user_uid}/report").status_code == 403
        assert user_uid not in {p["user_id"] for p in coach_client.get(f"{API}/coach/patients").json()}

    def test_unrelated_coach_still_forbidden_even_when_shared(self, paired, actors):
        user_client, user_uid = paired["user"][2], paired["user"][0]
        assert user_client.post(f"{API}/coach/share", json={"share": True}).status_code == 200
        other_coach_client = actors["coach_a"][2]
        r = other_coach_client.get(f"{API}/coach/patients/{user_uid}/report")
        assert r.status_code == 403, r.text
        user_client.post(f"{API}/coach/share", json={"share": False})

    def test_plain_user_role_forbidden_from_coach_endpoints(self, actors):
        r = actors["user_a"][2].get(f"{API}/coach/patients")
        assert r.status_code == 403, r.text
