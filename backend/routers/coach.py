"""Hair-coach layer: an admin-assigned 1:1 pairing between a plain user and a
coach, with the report only ever visible to the coach once the user opts in
(see admin.py's /users/{id}/coach for the pairing side)."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from models.database import db
from utils.deps import CurrentUser, require_roles
from models.schemas import CoachNoteIn, CoachShareIn
from services import sessions as sessions_service

router = APIRouter(prefix="/coach", tags=["coach"])


def _shared_with(patient: dict | None, coach_user_id: str) -> bool:
    return bool(patient and patient.get("coach_id") == coach_user_id and patient.get("share_with_coach"))


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
    if not _shared_with(patient, user["user_id"]):
        raise HTTPException(status_code=403, detail="Not shared with you")
    progress = await sessions_service.build_progress(patient_user_id)
    _, photos = await sessions_service.latest_photos_by_region(patient_user_id)
    return {
        "patient_name": patient.get("name", ""),
        "patient_email": patient.get("email", ""),
        "progress": progress,
        "recent_photos": photos,
    }


@router.get("/patients/{patient_user_id}/timeline")
async def patient_timeline(patient_user_id: str, user: CurrentUser):
    """Same shape as the patient's own GET /timeline (each session hydrated
    with images/analysis/coach_notes) -- lets the coach comment scan by scan
    instead of just seeing an aggregate trend."""
    require_roles(user, "coach")
    patient = await db.users.find_one({"user_id": patient_user_id}, {"_id": 0})
    if not _shared_with(patient, user["user_id"]):
        raise HTTPException(status_code=403, detail="Not shared with you")
    sessions = await db.tracking_sessions.find({"user_id": patient_user_id}, {"_id": 0}).sort("date", 1).to_list(1000)
    sessions = await sessions_service.attach_children(sessions)
    return await sessions_service.attach_coach_notes(sessions)


@router.post("/patients/{patient_user_id}/sessions/{session_id}/notes")
async def add_note(patient_user_id: str, session_id: str, body: CoachNoteIn, user: CurrentUser):
    require_roles(user, "coach")
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment can't be empty")
    patient = await db.users.find_one({"user_id": patient_user_id}, {"_id": 0})
    if not _shared_with(patient, user["user_id"]):
        raise HTTPException(status_code=403, detail="Not shared with you")
    session = await db.tracking_sessions.find_one({"id": session_id, "user_id": patient_user_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    note = {
        "id": str(uuid.uuid4()),
        "tracking_session_id": session_id,
        "patient_id": patient_user_id,
        "coach_id": user["user_id"],
        "coach_name": user.get("name", ""),
        "text": text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.coach_notes.insert_one(dict(note))
    note.pop("_id", None)
    return note
