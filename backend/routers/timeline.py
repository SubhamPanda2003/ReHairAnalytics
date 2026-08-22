"""Timeline listing and aggregate progress stats."""
from fastapi import APIRouter

from models.database import db
from utils.deps import CurrentUser
from services import sessions as sessions_service

router = APIRouter(tags=["timeline"])


@router.get("/timeline")
async def timeline(user: CurrentUser):
    sessions = await db.tracking_sessions.find({"user_id": user["user_id"]}, {"_id": 0}).sort("date", 1).to_list(1000)
    sessions = await sessions_service.attach_children(sessions)
    return await sessions_service.attach_coach_notes(sessions)


@router.get("/progress")
async def progress(user: CurrentUser):
    return await sessions_service.build_progress(user["user_id"])
