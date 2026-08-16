"""Patient <-> dermatologist appointment requests."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from models.database import db
from utils.deps import CurrentUser
from models.schemas import AppointmentIn
from services import sessions as sessions_service

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.post("")
async def create_appointment(body: AppointmentIn, user: CurrentUser):
    derm = await db.dermatologist_profiles.find_one({"user_id": body.dermatologist_id, "status": "approved"}, {"_id": 0})
    if not derm:
        raise HTTPException(status_code=404, detail="Dermatologist not available")
    doc = {
        "id": str(uuid.uuid4()),
        "patient_id": user["user_id"],
        "patient_name": user.get("name", ""),
        "patient_email": user.get("email", ""),
        "dermatologist_id": body.dermatologist_id,
        "derm_name": derm.get("name", ""),
        "requested_time": body.requested_time,
        "note": body.note or "",
        "status": "requested",
        "meeting_link": None,
        # Opt-in, per-appointment consent -- the dermatologist only ever sees a
        # patient's scan history/trend if this is True AND the appointment has
        # been confirmed (see /history below and files.py's ownership check).
        # Off by default; toggleable anytime via /share and /unshare, including
        # after booking, so consent is never locked in at request time.
        "share_history": bool(body.share_history),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.appointments.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_appointments(user: CurrentUser):
    as_patient = await db.appointments.find({"patient_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    as_derm = await db.appointments.find({"dermatologist_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"as_patient": as_patient, "as_dermatologist": as_derm}


@router.post("/{appt_id}/confirm")
async def confirm_appointment(appt_id: str, user: CurrentUser):
    appt = await db.appointments.find_one({"id": appt_id}, {"_id": 0})
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt["dermatologist_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    derm = await db.dermatologist_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    link = derm.get("meeting_link") if derm else None
    await db.appointments.update_one({"id": appt_id}, {"$set": {"status": "confirmed", "meeting_link": link}})
    return {"status": "confirmed", "meeting_link": link}


@router.post("/{appt_id}/decline")
async def decline_appointment(appt_id: str, user: CurrentUser):
    appt = await db.appointments.find_one({"id": appt_id}, {"_id": 0})
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt["dermatologist_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    await db.appointments.update_one({"id": appt_id}, {"$set": {"status": "declined"}})
    return {"status": "declined"}


@router.post("/{appt_id}/cancel")
async def cancel_appointment(appt_id: str, user: CurrentUser):
    appt = await db.appointments.find_one({"id": appt_id}, {"_id": 0})
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt["patient_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    await db.appointments.update_one({"id": appt_id}, {"$set": {"status": "cancelled"}})
    return {"status": "cancelled"}


@router.post("/{appt_id}/share")
async def share_history(appt_id: str, user: CurrentUser):
    """Patient opts in to let this appointment's dermatologist see their scan
    history/trend. Independent of booking -- can be turned on any time."""
    appt = await db.appointments.find_one({"id": appt_id}, {"_id": 0})
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt["patient_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    await db.appointments.update_one({"id": appt_id}, {"$set": {"share_history": True}})
    return {"share_history": True}


@router.post("/{appt_id}/unshare")
async def unshare_history(appt_id: str, user: CurrentUser):
    """Revokes a prior /share -- takes effect immediately since the
    dermatologist's /history read is gated live on this flag, not a copy."""
    appt = await db.appointments.find_one({"id": appt_id}, {"_id": 0})
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt["patient_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    await db.appointments.update_one({"id": appt_id}, {"$set": {"share_history": False}})
    return {"share_history": False}


@router.get("/{appt_id}/history")
async def patient_history(appt_id: str, user: CurrentUser):
    """The shared patient's scan-score trend + latest photos for this
    appointment's dermatologist -- only once the patient has opted in AND the
    dermatologist has actually confirmed the appointment (a pending request
    they haven't accepted yet shouldn't already see the patient's history)."""
    appt = await db.appointments.find_one({"id": appt_id}, {"_id": 0})
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt["dermatologist_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    if appt["status"] != "confirmed" or not appt.get("share_history"):
        raise HTTPException(status_code=403, detail="Patient hasn't shared their history for this appointment")

    patient_id = appt["patient_id"]
    progress = await sessions_service.build_progress(patient_id)
    _, photos = await sessions_service.latest_photos_by_region(patient_id)
    return {
        "patient_name": appt.get("patient_name", ""),
        "patient_email": appt.get("patient_email", ""),
        "progress": progress,
        "recent_photos": photos,
    }
