"""Admin/super-admin moderation: dermatologist approval and user roles."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from utils import config
from models.database import db
from utils.deps import CurrentUser, require_roles
from models.schemas import RoleIn

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
