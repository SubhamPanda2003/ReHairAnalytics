"""Admin/super-admin moderation: dermatologist approval, user roles, and
scan-credit management."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from utils import config
from models.database import db
from utils.deps import CurrentUser, require_roles
from models.schemas import CoachAssignIn, RoleIn, ScanLimitIn, SettingsIn
from services import quota as quota_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dermatologists")
async def admin_list_derms(user: CurrentUser, status: Optional[str] = Query(None)):
    require_roles(user, "admin", "super_admin")
    q = {"status": status} if status else {}
    return await db.dermatologist_profiles.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.post("/dermatologists/{derm_user_id}/approve")
async def admin_approve_derm(derm_user_id: str, user: CurrentUser):
    require_roles(user, "admin", "super_admin")
    r = await db.dermatologist_profiles.update_one({"user_id": derm_user_id}, {"$set": {"status": "approved"}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Dermatologist not found")
    return {"status": "approved"}


@router.post("/dermatologists/{derm_user_id}/reject")
async def admin_reject_derm(derm_user_id: str, user: CurrentUser):
    require_roles(user, "admin", "super_admin")
    r = await db.dermatologist_profiles.update_one({"user_id": derm_user_id}, {"$set": {"status": "rejected"}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Dermatologist not found")
    return {"status": "rejected"}


@router.delete("/dermatologists/{derm_user_id}")
async def admin_delete_derm(derm_user_id: str, user: CurrentUser):
    """Permanently removes a dermatologist's profile (pending, approved, or
    rejected). Reverts their account role back to "user" -- mirrors
    derm_register's own promotion, and avoids leaving them stuck as
    role="dermatologist" with no profile behind it (derm/me would return
    {}, derm-only pages would have nothing to show). Any of their
    appointments still requested/confirmed get cancelled rather than left
    pointing at a dermatologist who no longer exists; already-declined or
    -cancelled ones are left alone since there's nothing live to clean up."""
    require_roles(user, "admin", "super_admin")
    derm = await db.dermatologist_profiles.find_one({"user_id": derm_user_id}, {"_id": 0})
    if not derm:
        raise HTTPException(status_code=404, detail="Dermatologist not found")
    await db.dermatologist_profiles.delete_one({"user_id": derm_user_id})
    target = await db.users.find_one({"user_id": derm_user_id}, {"_id": 0})
    if target and target.get("role") == "dermatologist":
        await db.users.update_one({"user_id": derm_user_id}, {"$set": {"role": "user"}})
    await db.appointments.update_many(
        {"dermatologist_id": derm_user_id, "status": {"$in": ["requested", "confirmed"]}},
        {"$set": {"status": "cancelled"}},
    )
    return {"deleted": True, "user_id": derm_user_id}


@router.get("/users")
async def admin_list_users(user: CurrentUser):
    require_roles(user, "super_admin")
    users = await db.users.find({}, {"_id": 0, "user_id": 1, "email": 1, "name": 1, "picture": 1, "role": 1, "phone": 1}).to_list(2000)
    for u in users:
        u.setdefault("role", "user")
    return users


@router.post("/users/{target_user_id}/role")
async def admin_set_role(target_user_id: str, body: RoleIn, user: CurrentUser):
    require_roles(user, "super_admin")
    if body.role not in ("user", "admin", "coach"):
        raise HTTPException(status_code=400, detail="Role must be 'user', 'admin' or 'coach'")
    target = await db.users.find_one({"user_id": target_user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("email", "").lower() == config.SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=400, detail="Cannot change the super admin")
    await db.users.update_one({"user_id": target_user_id}, {"$set": {"role": body.role}})
    return {"user_id": target_user_id, "role": body.role}


@router.get("/scan-usage")
async def admin_scan_usage(user: CurrentUser):
    """How many reports each user has generated (scan_count) and how many
    credits that actually cost them (credits_used -- precision scans cost
    more, see services.quota), plus their scan-credit limit (raw per-user
    override and the effective limit after falling back to the global
    default). Open to admin + super_admin, unlike /users which stays
    super_admin-only since it also exposes role management."""
    require_roles(user, "admin", "super_admin")
    users = await db.users.find(
        {}, {"_id": 0, "user_id": 1, "email": 1, "name": 1, "role": 1, "scan_limit": 1, "credits_reset_at": 1}
    ).to_list(2000)
    counts = {
        row["_id"]: row["count"]
        for row in await db.tracking_sessions.aggregate([{"$group": {"_id": "$user_id", "count": {"$sum": 1}}}]).to_list(2000)
    }
    rows = []
    for u in users:
        u.setdefault("role", "user")
        scan_count = counts.get(u["user_id"], 0)
        # Per-user, not batched -- each user may have their own
        # credits_reset_at cutoff (see admin_set_scan_limit), so a single
        # blanket aggregation across everyone can't compute this correctly.
        credits = await quota_service.credits_used(u["user_id"], since=u.get("credits_reset_at"))
        effective = await quota_service.effective_limit(u)
        remaining = None if effective is None else max(0, effective - credits)
        rows.append({
            "user_id": u["user_id"],
            "name": u.get("name"),
            "email": u.get("email"),
            "role": u["role"],
            "scan_count": scan_count,
            "credits_used": credits,
            "scan_limit": u.get("scan_limit"),
            "effective_limit": effective,
            "remaining": remaining,
        })
    return rows


@router.post("/users/{target_user_id}/scan-limit")
async def admin_set_scan_limit(target_user_id: str, body: ScanLimitIn, user: CurrentUser):
    """Setting (or clearing) a user's limit is treated as a fresh credit
    grant -- credits_reset_at is stamped on every call, so usage accrued
    before this point stops counting against the new limit (see
    services.quota.credits_used). Scan history itself isn't touched, only
    what counts toward the current allocation, so "reports generated"
    elsewhere in the admin view stays a true lifetime count."""
    require_roles(user, "admin", "super_admin")
    if body.scan_limit is not None and body.scan_limit < 0:
        raise HTTPException(status_code=400, detail="scan_limit must be 0 or greater")
    target = await db.users.find_one({"user_id": target_user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    reset_at = datetime.now(timezone.utc).isoformat()
    await db.users.update_one(
        {"user_id": target_user_id}, {"$set": {"scan_limit": body.scan_limit, "credits_reset_at": reset_at}}
    )
    target["scan_limit"] = body.scan_limit
    target["credits_reset_at"] = reset_at
    effective = await quota_service.effective_limit(target)
    used = await quota_service.credits_used(target_user_id, since=reset_at)
    remaining = None if effective is None else max(0, effective - used)
    return {
        "user_id": target_user_id, "scan_limit": body.scan_limit, "effective_limit": effective,
        "used": used, "remaining": remaining,
    }


@router.get("/settings")
async def admin_get_settings(user: CurrentUser):
    require_roles(user, "admin", "super_admin")
    return await quota_service.get_settings()


@router.post("/settings")
async def admin_update_settings(body: SettingsIn, user: CurrentUser):
    require_roles(user, "admin", "super_admin")
    patch = body.model_dump(exclude_unset=True)
    return await quota_service.update_settings(patch)


@router.get("/coaches")
async def admin_list_coaches(user: CurrentUser):
    """Coach roster for the assignment dropdown -- accounts already promoted
    to role="coach" via /admin/users/{id}/role (super_admin-only, same as
    'admin')."""
    require_roles(user, "admin", "super_admin")
    return await db.users.find({"role": "coach"}, {"_id": 0, "user_id": 1, "name": 1, "email": 1}).to_list(500)


@router.get("/coach-assignments")
async def admin_coach_assignments(user: CurrentUser):
    """Every plain user's current coach pairing plus whether they've actually
    opted in to share reports -- the pairing alone doesn't grant the coach
    anything (see routers/coach.py), so both columns matter to whoever's
    reading this list."""
    require_roles(user, "admin", "super_admin")
    coaches = {
        c["user_id"]: c.get("name", "")
        for c in await db.users.find({"role": "coach"}, {"_id": 0, "user_id": 1, "name": 1}).to_list(500)
    }
    users = await db.users.find(
        {"role": {"$nin": ["admin", "super_admin", "coach", "dermatologist"]}},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "coach_id": 1, "share_with_coach": 1},
    ).to_list(2000)
    return [
        {
            "user_id": u["user_id"],
            "name": u.get("name"),
            "email": u.get("email"),
            "coach_id": u.get("coach_id"),
            "coach_name": coaches.get(u.get("coach_id")) if u.get("coach_id") else None,
            "share_with_coach": bool(u.get("share_with_coach")),
        }
        for u in users
    ]


@router.post("/users/{target_user_id}/coach")
async def admin_assign_coach(target_user_id: str, body: CoachAssignIn, user: CurrentUser):
    """Pairing is admin-managed and 1:1. Setting or changing it always resets
    share_with_coach back to False so a user's reports don't silently stay
    visible to whoever the *new* coach is without them re-consenting (mirrors
    how admin_set_scan_limit stamps a fresh credits_reset_at on every call)."""
    require_roles(user, "admin", "super_admin")
    target = await db.users.find_one({"user_id": target_user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if body.coach_id is not None:
        coach = await db.users.find_one({"user_id": body.coach_id, "role": "coach"}, {"_id": 0})
        if not coach:
            raise HTTPException(status_code=404, detail="Coach not found")
    await db.users.update_one(
        {"user_id": target_user_id}, {"$set": {"coach_id": body.coach_id, "share_with_coach": False}}
    )
    return {"user_id": target_user_id, "coach_id": body.coach_id, "share_with_coach": False}
