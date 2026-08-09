"""Dermatologist self-registration and the public directory."""
from datetime import datetime, timezone

from fastapi import APIRouter

from models.database import db
from utils.deps import CurrentUser
from models.schemas import DermRegisterIn

router = APIRouter(tags=["dermatologists"])


def _derm_public(d: dict, include_link: bool = False) -> dict:
    out = {
        "user_id": d.get("user_id"),
        "name": d.get("name"),
        "specialty": d.get("specialty"),
        "years_experience": d.get("years_experience"),
        "bio": d.get("bio"),
        "photo": d.get("photo"),
        "price": d.get("price"),
        "status": d.get("status"),
    }
    if include_link:
        out["meeting_link"] = d.get("meeting_link")
    return out


@router.post("/derm/register")
async def derm_register(body: DermRegisterIn, user: CurrentUser):
    existing = await db.dermatologist_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if existing:
        status = existing.get("status", "pending")
        # Re-review if a previously approved dermatologist changes key public details.
        if status == "approved" and (
            existing.get("name") != body.name
            or existing.get("specialty") != body.specialty
            or existing.get("meeting_link") != body.meeting_link
        ):
            status = "pending"
    else:
        status = "pending"
    doc = {
        "user_id": user["user_id"],
        "email": user.get("email"),
        "name": body.name,
        "specialty": body.specialty,
        "years_experience": body.years_experience,
        "bio": body.bio or "",
        "photo": body.photo or user.get("picture", ""),
        "meeting_link": body.meeting_link,
        "price": body.price or "",
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        await db.dermatologist_profiles.update_one({"user_id": user["user_id"]}, {"$set": doc})
    else:
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.dermatologist_profiles.insert_one(dict(doc))
    # promote role to dermatologist unless already admin/super_admin
    if user.get("role") not in ("admin", "super_admin"):
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"role": "dermatologist"}})
    doc.pop("_id", None)
    return doc


@router.get("/derm/me")
async def derm_me(user: CurrentUser):
    d = await db.dermatologist_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return d or {}


@router.get("/dermatologists")
async def list_dermatologists(_user: CurrentUser):
    docs = await db.dermatologist_profiles.find({"status": "approved"}, {"_id": 0}).to_list(500)
    return [_derm_public(d) for d in docs]
