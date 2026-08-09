"""Pydantic request bodies."""
from typing import Optional

from pydantic import BaseModel


class SessionExchange(BaseModel):
    session_id: str


class ProfileIn(BaseModel):
    age: Optional[int] = None
    gender: Optional[str] = None
    hair_type: Optional[str] = None
    goals: Optional[str] = None
    reminder_enabled: Optional[bool] = None
    reminder_day: Optional[str] = None


class SessionIn(BaseModel):
    notes: Optional[str] = ""


class DermRegisterIn(BaseModel):
    name: str
    specialty: str
    years_experience: Optional[int] = None
    bio: Optional[str] = ""
    photo: Optional[str] = ""
    meeting_link: str
    price: Optional[str] = ""


class AppointmentIn(BaseModel):
    dermatologist_id: str
    requested_time: str
    note: Optional[str] = ""


class RoleIn(BaseModel):
    role: str
