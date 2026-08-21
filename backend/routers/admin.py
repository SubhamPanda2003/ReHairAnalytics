"""Admin/super-admin moderation: dermatologist approval, user roles, and
scan-credit management."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from utils import config
from models.database import db
from utils.deps import CurrentUser, require_roles
from models.schemas import RoleIn, ScanLimitIn, SettingsIn
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
    users = await db.users.find({}, {"_id": 0, "user_id": 1, "email": 1, "name": 1, "picture": 1, "role": 1}).to_list(2000)
    for u in users:
        u.setdefault("role", "user")
    return users


@router.post("/users/{target_user_id}/role")
async def admin_set_role(target_user_id: str, body: RoleIn, user: CurrentUser):
    require_roles(user, "super_admin")
    if body.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Role must be 'user' or 'admin'")
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
    users = await db.users.find({}, {"_id": 0, "user_id": 1, "email": 1, "name": 1, "role": 1, "scan_limit": 1}).to_list(2000)
    agg = {
        row["_id"]: row
        for row in await db.tracking_sessions.aggregate([
            {"$group": {
                "_id": "$user_id",
                "count": {"$sum": 1},
                "credits": {"$sum": {"$ifNull": ["$credits_used", quota_service.SCAN_CREDIT_COST]}},
            }},
        ]).to_list(2000)
    }
    settings = await quota_service.get_settings()
    rows = []
    for u in users:
        u.setdefault("role", "user")
        agg_row = agg.get(u["user_id"], {})
        scan_count = agg_row.get("count", 0)
        credits = agg_row.get("credits", 0)
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
    require_roles(user, "admin", "super_admin")
    if body.scan_limit is not None and body.scan_limit < 0:
        raise HTTPException(status_code=400, detail="scan_limit must be 0 or greater")
    target = await db.users.find_one({"user_id": target_user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one({"user_id": target_user_id}, {"$set": {"scan_limit": body.scan_limit}})
    target["scan_limit"] = body.scan_limit
    effective = await quota_service.effective_limit(target)
    return {"user_id": target_user_id, "scan_limit": body.scan_limit, "effective_limit": effective}


@router.get("/settings")
async def admin_get_settings(user: CurrentUser):
    require_roles(user, "admin", "super_admin")
    return await quota_service.get_settings()


@router.post("/settings")
async def admin_update_settings(body: SettingsIn, user: CurrentUser):
    require_roles(user, "admin", "super_admin")
    patch = body.model_dump(exclude_unset=True)
    return await quota_service.update_settings(patch)
