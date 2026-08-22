"""User hair-tracking profile (age, gender, goals, reminders)."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter

from models.database import db
from utils.deps import CurrentUser
from models.schemas import ProfileIn

router = APIRouter(tags=["profile"])


@router.get("/profile")
async def get_profile(user: CurrentUser):
    profile = await db.profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return profile or {}


@router.post("/profile")
async def upsert_profile(body: ProfileIn, user: CurrentUser):
    doc = body.model_dump(exclude_unset=True)
    # phone is contact info, not hair-tracking context -- lives on the user
    # doc (so admin's user list can show it alongside email with no join),
    # not duplicated into this collection. Popped out before the profiles
    # write and only added back to the RESPONSE afterward, so it never
    # actually lands in `profiles`.
    phone_provided = "phone" in doc
    phone = doc.pop("phone", None)
    if phone_provided:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"phone": phone}})
    doc["user_id"] = user["user_id"]
    existing = await db.profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if existing:
        await db.profiles.update_one({"user_id": user["user_id"]}, {"$set": doc})
    else:
        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.profiles.insert_one(dict(doc))
    doc.pop("_id", None)
    if phone_provided:
        doc["phone"] = phone
    return doc
