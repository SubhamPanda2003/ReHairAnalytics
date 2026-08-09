"""Data export and account deletion."""
from datetime import datetime, timezone

from fastapi import APIRouter, Response

from models.database import db
from utils.deps import CurrentUser

router = APIRouter(tags=["account"])


@router.get("/export")
async def export_data(user: CurrentUser):
    profile = await db.profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    sessions = await db.tracking_sessions.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    images = await db.images.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    analysis = await db.analysis.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {"name": user.get("name"), "email": user.get("email")},
        "profile": profile,
        "tracking_sessions": sessions,
        "images": images,
        "analysis": analysis,
    }


@router.delete("/account")
async def delete_account(user: CurrentUser, response: Response):
    uid = user["user_id"]
    await db.images.update_many({"user_id": uid}, {"$set": {"is_deleted": True}})
    await db.images.delete_many({"user_id": uid})
    await db.analysis.delete_many({"user_id": uid})
    await db.tracking_sessions.delete_many({"user_id": uid})
    await db.profiles.delete_many({"user_id": uid})
    await db.user_sessions.delete_many({"user_id": uid})
    await db.users.delete_many({"user_id": uid})
    response.delete_cookie("session_token", path="/")
    return {"deleted": True}
