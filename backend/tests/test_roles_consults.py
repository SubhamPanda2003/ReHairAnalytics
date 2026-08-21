"""Iteration-3 backend tests: RBAC roles, dermatologist registration/approval,
admin user management, and appointment request/confirm/decline/cancel flows.

Seeds isolated users directly in MongoDB (test_database) per
/app/memory/test_credentials.md and authenticates with Bearer <session_token>.
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
    """super_admin (by email), plain user, derm candidate."""
    created = []
    sa = _seed(db, "superadmin", email=SUPER_ADMIN_EMAIL)
    plain = _seed(db, "plainuser")
    derm = _seed(db, "dermcand")
    created += [sa[0], plain[0], derm[0]]
    yield {"sa": sa, "user": plain, "derm": derm}
    for uid in created:
        db.users.delete_many({"user_id": uid})
        db.user_sessions.delete_many({"user_id": uid})
        db.dermatologist_profiles.delete_many({"user_id": uid})
        db.appointments.delete_many({"patient_id": uid})
        db.appointments.delete_many({"dermatologist_id": uid})


# ---------------------------------------------------------------- roles
class TestRoles:
    def test_super_admin_by_email(self, actors):
        r = actors["sa"][2].get(f"{API}/auth/me")
        assert r.status_code == 200, r.text
        me = r.json()
        assert me["email"].lower() == SUPER_ADMIN_EMAIL
        assert me["role"] == "super_admin", me
        assert "_id" not in me

    def test_plain_user_role(self, actors):
        r = actors["user"][2].get(f"{API}/auth/me")
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "user"

    def test_rbac_plain_user_forbidden_admin_endpoints(self, actors):
        c = actors["user"][2]
        assert c.get(f"{API}/admin/users").status_code == 403
        assert c.get(f"{API}/admin/dermatologists").status_code == 403

    def test_unauthenticated_admin_endpoint_401(self):
        assert requests.get(f"{API}/admin/dermatologists").status_code == 401


# ------------------------------------------------- derm register/approve
class TestDermatologistLifecycle:
    payload = {
        "name": "TEST Dr. Alice Roy",
        "specialty": "Trichology",
        "years_experience": 9,
        "bio": "TEST bio for hair loss",
        "photo": "",
        "meeting_link": "https://meet.google.com/test-abc-xyz",
        "price": "$50",
    }

    @pytest.fixture(scope="class")
    def own_derm(self, db):
        """Isolated derm user for this class (TestAppointments uses its own,
        and under xdist loadscope class order is not guaranteed)."""
        uid, _, c = _seed(db, "dermlifecycle")
        yield uid, c
        db.users.delete_many({"user_id": uid})
        db.user_sessions.delete_many({"user_id": uid})
        db.dermatologist_profiles.delete_many({"user_id": uid})

    def test_01_register_creates_pending_and_flips_role(self, own_derm):
        uid, c = own_derm
        r = c.post(f"{API}/derm/register", json=self.payload)
        assert r.status_code == 200, r.text
        body = r.json()
        prof = body.get("profile") or body
        assert prof["status"] == "pending", body
        assert prof["name"] == self.payload["name"]
        assert prof["specialty"] == self.payload["specialty"]
        # role flipped
        me = c.get(f"{API}/auth/me").json()
        assert me["role"] == "dermatologist", me

    def test_02_derm_me_returns_profile(self, own_derm):
        r = own_derm[1].get(f"{API}/derm/me")
        assert r.status_code == 200, r.text
        d = r.json()
        prof = d.get("profile") or d
        assert prof["meeting_link"] == self.payload["meeting_link"]
        assert prof["status"] == "pending"

    def test_03_pending_not_in_public_list(self, actors, own_derm):
        uid = own_derm[0]
        r = actors["user"][2].get(f"{API}/dermatologists")
        assert r.status_code == 200, r.text
        assert all(d["user_id"] != uid for d in r.json()), "pending derm leaked to public list"

    def test_04_admin_sees_pending(self, actors, own_derm):
        uid = own_derm[0]
        r = actors["sa"][2].get(f"{API}/admin/dermatologists")
        assert r.status_code == 200, r.text
        rows = r.json()
        match = [d for d in rows if d["user_id"] == uid]
        assert match, f"pending derm {uid} not listed for admin"
        assert match[0]["status"] == "pending"

    def test_05_approve_then_public_list_without_link(self, actors, own_derm):
        uid = own_derm[0]
        r = actors["sa"][2].post(f"{API}/admin/dermatologists/{uid}/approve")
        assert r.status_code == 200, r.text
        pub = actors["user"][2].get(f"{API}/dermatologists")
        assert pub.status_code == 200
        match = [d for d in pub.json() if d["user_id"] == uid]
        assert match, "approved derm missing from public list"
        d = match[0]
        assert d["name"] == self.payload["name"]
        assert "meeting_link" not in d, "meeting_link leaked in public list"
        assert "_id" not in d

    def test_06_approve_unknown_user_404(self, actors):
        r = actors["sa"][2].post(f"{API}/admin/dermatologists/no-such-uid/approve")
        assert r.status_code == 404, r.text

    def test_07_reject_then_reapprove(self, actors, db, own_derm):
        uid = own_derm[0]
        r = actors["sa"][2].post(f"{API}/admin/dermatologists/{uid}/reject")
        assert r.status_code == 200, r.text
        assert db.dermatologist_profiles.find_one({"user_id": uid})["status"] == "rejected"
        pub = actors["user"][2].get(f"{API}/dermatologists").json()
        assert all(d["user_id"] != uid for d in pub)
        # restore approved for appointment tests
        assert actors["sa"][2].post(f"{API}/admin/dermatologists/{uid}/approve").status_code == 200


# ---------------------------------------------------- derm deletion (admin)
class TestDermatologistDeletion:
    payload = {
        "name": "TEST Dr. Delete Me",
        "specialty": "Trichology",
        "years_experience": 5,
        "bio": "",
        "photo": "",
        "meeting_link": "https://meet.google.com/test-del-xyz",
        "price": "$40",
    }

    @pytest.fixture(scope="class")
    def own_derm(self, db):
        uid, _, c = _seed(db, "dermdelete")
        yield uid, c
        db.users.delete_many({"user_id": uid})
        db.user_sessions.delete_many({"user_id": uid})
        db.dermatologist_profiles.delete_many({"user_id": uid})

    @pytest.fixture(scope="class")
    def own_patient(self, db):
        uid, _, c = _seed(db, "dermdeletepatient")
        yield uid, c
        db.users.delete_many({"user_id": uid})
        db.user_sessions.delete_many({"user_id": uid})
        db.appointments.delete_many({"patient_id": uid})

    def test_00_setup_approved_derm_with_appointment(self, actors, own_derm, own_patient):
        uid, c = own_derm
        r = c.post(f"{API}/derm/register", json=self.payload)
        assert r.status_code == 200, r.text
        assert actors["sa"][2].post(f"{API}/admin/dermatologists/{uid}/approve").status_code == 200
        when = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        ar = own_patient[1].post(f"{API}/appointments", json={
            "dermatologist_id": uid, "requested_time": when, "note": "TEST pre-delete booking",
        })
        assert ar.status_code == 200, ar.text
        type(self).appt_id = ar.json()["id"]

    def test_01_plain_user_forbidden(self, actors, own_derm):
        r = actors["user"][2].delete(f"{API}/admin/dermatologists/{own_derm[0]}")
        assert r.status_code == 403, r.text

    def test_02_unknown_user_404(self, actors):
        r = actors["sa"][2].delete(f"{API}/admin/dermatologists/no-such-uid")
        assert r.status_code == 404, r.text

    def test_03_admin_deletes_derm(self, actors, own_derm, db):
        uid = own_derm[0]
        r = actors["sa"][2].delete(f"{API}/admin/dermatologists/{uid}")
        assert r.status_code == 200, r.text
        assert r.json() == {"deleted": True, "user_id": uid}

        assert db.dermatologist_profiles.find_one({"user_id": uid}) is None
        pub = actors["user"][2].get(f"{API}/dermatologists").json()
        assert all(d["user_id"] != uid for d in pub), "deleted derm still in public list"
        admin_list = actors["sa"][2].get(f"{API}/admin/dermatologists").json()
        assert all(d["user_id"] != uid for d in admin_list), "deleted derm still in admin list"

    def test_04_role_reverted_to_user(self, own_derm):
        me = own_derm[1].get(f"{API}/auth/me").json()
        assert me["role"] == "user", me

    def test_05_derm_me_now_empty(self, own_derm):
        r = own_derm[1].get(f"{API}/derm/me")
        assert r.status_code == 200, r.text
        assert r.json() == {}

    def test_06_pending_appointment_cancelled(self, db):
        appt = db.appointments.find_one({"id": self.appt_id}, {"_id": 0})
        assert appt["status"] == "cancelled", appt

    def test_07_delete_again_404(self, actors, own_derm):
        r = actors["sa"][2].delete(f"{API}/admin/dermatologists/{own_derm[0]}")
        assert r.status_code == 404, r.text


# ------------------------------------------------------- admin user mgmt
class TestAdminUsers:
    def test_list_users_super_admin(self, actors):
        r = actors["sa"][2].get(f"{API}/admin/users")
        assert r.status_code == 200, r.text
        users = r.json()
        assert isinstance(users, list) and len(users) >= 3
        assert all("_id" not in u for u in users)
        assert all("role" in u for u in users)

    def test_promote_and_demote(self, actors):
        target = actors["user"][0]
        r = actors["sa"][2].post(f"{API}/admin/users/{target}/role", json={"role": "admin"})
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "admin"
        # verify via /auth/me of that user
        assert actors["user"][2].get(f"{API}/auth/me").json()["role"] == "admin"
        # promoted user can now hit admin derm list but NOT users list (super_admin only)
        assert actors["user"][2].get(f"{API}/admin/dermatologists").status_code == 200
        assert actors["user"][2].get(f"{API}/admin/users").status_code == 403
        # demote back
        r2 = actors["sa"][2].post(f"{API}/admin/users/{target}/role", json={"role": "user"})
        assert r2.status_code == 200, r2.text
        assert actors["user"][2].get(f"{API}/auth/me").json()["role"] == "user"

    def test_cannot_change_super_admin(self, actors):
        r = actors["sa"][2].post(f"{API}/admin/users/{actors['sa'][0]}/role", json={"role": "user"})
        assert r.status_code == 400, r.text

    def test_invalid_role_400(self, actors):
        r = actors["sa"][2].post(f"{API}/admin/users/{actors['user'][0]}/role",
                                 json={"role": "super_admin"})
        assert r.status_code == 400, r.text

    def test_unknown_target_404(self, actors):
        r = actors["sa"][2].post(f"{API}/admin/users/nope-uid/role", json={"role": "admin"})
        assert r.status_code == 404, r.text


# ----------------------------------------------------------- appointments
class TestAppointments:
    def test_00_setup_approved_derm(self, actors):
        """Self-contained: register + approve the derm (xdist loadscope may run
        this class on a different worker than TestDermatologistLifecycle)."""
        uid, _, c = actors["derm"]
        r = c.post(f"{API}/derm/register", json=TestDermatologistLifecycle.payload)
        assert r.status_code == 200, r.text
        assert actors["sa"][2].post(f"{API}/admin/dermatologists/{uid}/approve").status_code == 200
        pub = actors["user"][2].get(f"{API}/dermatologists").json()
        assert any(d["user_id"] == uid for d in pub)

    def test_01_request_appointment(self, actors):
        derm_uid = actors["derm"][0]
        when = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        r = actors["user"][2].post(f"{API}/appointments", json={
            "dermatologist_id": derm_uid,
            "requested_time": when,
            "note": "TEST thinning at crown",
        })
        assert r.status_code == 200, r.text
        a = r.json().get("appointment") or r.json()
        assert a["status"] == "requested", a
        assert a["dermatologist_id"] == derm_uid
        assert a.get("meeting_link") in (None, "")
        assert "_id" not in a
        type(self).appt_id = a["id"]

    def test_02_appointment_unknown_derm_404(self, actors):
        r = actors["user"][2].post(f"{API}/appointments", json={
            "dermatologist_id": "not-a-derm",
            "requested_time": datetime.now(timezone.utc).isoformat(),
            "note": "",
        })
        assert r.status_code == 404, r.text

    def test_03_list_as_patient_and_as_derm(self, actors):
        rp = actors["user"][2].get(f"{API}/appointments")
        assert rp.status_code == 200, rp.text
        pdata = rp.json()
        assert any(x["id"] == self.appt_id for x in pdata["as_patient"])
        assert pdata["as_dermatologist"] == []

        rd = actors["derm"][2].get(f"{API}/appointments")
        assert rd.status_code == 200
        ddata = rd.json()
        assert any(x["id"] == self.appt_id for x in ddata["as_dermatologist"])
        # link not revealed before confirm
        row = [x for x in ddata["as_dermatologist"] if x["id"] == self.appt_id][0]
        assert row["status"] == "requested"

    def test_04_non_owner_cannot_confirm(self, actors):
        r = actors["user"][2].post(f"{API}/appointments/{self.appt_id}/confirm")
        assert r.status_code == 403, r.text

    def test_05_derm_confirms_reveals_link(self, actors):
        r = actors["derm"][2].post(f"{API}/appointments/{self.appt_id}/confirm")
        assert r.status_code == 200, r.text
        body = r.json()
        a = body.get("appointment") or body
        assert a["status"] == "confirmed"
        assert a["meeting_link"] == TestDermatologistLifecycle.payload["meeting_link"]
        # patient now sees confirmed + link
        pdata = actors["user"][2].get(f"{API}/appointments").json()
        row = [x for x in pdata["as_patient"] if x["id"] == self.appt_id][0]
        assert row["status"] == "confirmed"
        assert row["meeting_link"] == TestDermatologistLifecycle.payload["meeting_link"]

    def test_06_patient_cancel(self, actors):
        r = actors["user"][2].post(f"{API}/appointments/{self.appt_id}/cancel")
        assert r.status_code == 200, r.text
        pdata = actors["user"][2].get(f"{API}/appointments").json()
        row = [x for x in pdata["as_patient"] if x["id"] == self.appt_id][0]
        assert row["status"] == "cancelled"

    def test_07_decline_flow_and_403(self, actors):
        derm_uid = actors["derm"][0]
        r = actors["user"][2].post(f"{API}/appointments", json={
            "dermatologist_id": derm_uid,
            "requested_time": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "note": "TEST second request",
        })
        assert r.status_code == 200, r.text
        aid = (r.json().get("appointment") or r.json())["id"]
        # patient cannot decline
        assert actors["user"][2].post(f"{API}/appointments/{aid}/decline").status_code == 403
        assert actors["derm"][2].post(f"{API}/appointments/{aid}/decline").status_code == 200
        pdata = actors["user"][2].get(f"{API}/appointments").json()
        row = [x for x in pdata["as_patient"] if x["id"] == aid][0]
        assert row["status"] == "declined"
        assert not row.get("meeting_link")

    def test_08_unknown_appointment_404(self, actors):
        assert actors["derm"][2].post(f"{API}/appointments/nope/confirm").status_code == 404
        assert actors["user"][2].post(f"{API}/appointments/nope/cancel").status_code == 404

    def test_09_appointments_requires_auth(self):
        assert requests.get(f"{API}/appointments").status_code == 401
