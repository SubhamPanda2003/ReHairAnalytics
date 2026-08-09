"""Patient <-> dermatologist appointment requests."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from models.database import db
from utils.deps import CurrentUser
from models.schemas import AppointmentIn

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
