"""Hair-coach layer: an admin-assigned 1:1 pairing between a plain user and a
coach, with the report only ever visible to the coach once the user opts in
(see admin.py's /users/{id}/coach for the pairing side)."""
from fastapi import APIRouter, HTTPException

from models.database import db
from utils.deps import CurrentUser, require_roles
from models.schemas import CoachShareIn
from services import sessions as sessions_service

router = APIRouter(prefix="/coach", tags=["coach"])


@router.get("/mine")
async def my_coach(user: CurrentUser):
    coach_id = user.get("coach_id")
    coach = None
    if coach_id:
        coach = await db.users.find_one(
            {"user_id": coach_id, "role": "coach"}, {"_id": 0, "user_id": 1, "name": 1, "picture": 1}
        )
    return {"coach": coach, "share_with_coach": bool(user.get("share_with_coach"))}


@router.post("/share")
async def set_share(body: CoachShareIn, user: CurrentUser):
    """Independent of the pairing itself -- can be flipped on or off anytime,
    same opt-in-anytime model as appointments.py's dermatologist /share."""
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"share_with_coach": bool(body.share)}})
    return {"share_with_coach": bool(body.share)}


@router.get("/patients")
async def list_patients(user: CurrentUser):
    require_roles(user, "coach")
    return await db.users.find(
        {"coach_id": user["user_id"], "share_with_coach": True},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1},
    ).to_list(500)


@router.get("/patients/{patient_user_id}/report")
async def patient_report(patient_user_id: str, user: CurrentUser):
    require_roles(user, "coach")
    patient = await db.users.find_one({"user_id": patient_user_id}, {"_id": 0})
    if not patient or patient.get("coach_id") != user["user_id"] or not patient.get("share_with_coach"):
        raise HTTPException(status_code=403, detail="Not shared with you")
    progress = await sessions_service.build_progress(patient_user_id)
    _, photos = await sessions_service.latest_photos_by_region(patient_user_id)
    return {
        "patient_name": patient.get("name", ""),
        "patient_email": patient.get("email", ""),
        "progress": progress,
        "recent_photos": photos,
    }
