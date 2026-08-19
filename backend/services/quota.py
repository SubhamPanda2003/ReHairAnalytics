"""Scan-credit quota: global default limit + per-user overrides, and the
configurable message shown once a user runs out."""
from typing import Optional

from models.database import db

SETTINGS_ID = "global"

DEFAULT_SETTINGS = {
    "default_scan_limit": None,  # None = unlimited
    "exhausted_message": "You've used all your available scans.",
    "whatsapp_number": "+91 6281482850",
}

# Only plain "user" accounts are ever scan-limited -- admins, dermatologists,
# and the super admin need unrestricted access regardless of any scan_limit
# value that happens to be sitting on their user doc.
LIMITED_ROLES = {"user"}


async def get_settings() -> dict:
    doc = await db.app_settings.find_one({"key": SETTINGS_ID}, {"_id": 0}) or {}
    return {**DEFAULT_SETTINGS, **doc}


async def update_settings(patch: dict) -> dict:
    if patch:
        await db.app_settings.update_one({"key": SETTINGS_ID}, {"$set": patch}, upsert=True)
    return await get_settings()


async def scan_count(user_id: str) -> int:
    return await db.tracking_sessions.count_documents({"user_id": user_id})


async def effective_limit(user: dict) -> Optional[int]:
    if user.get("role", "user") not in LIMITED_ROLES:
        return None
    override = user.get("scan_limit")
    if override is not None:
        return override
    settings = await get_settings()
    return settings["default_scan_limit"]


async def quota_for(user: dict) -> dict:
    settings = await get_settings()
    limit = await effective_limit(user)
    used = await scan_count(user["user_id"])
    remaining = None if limit is None else max(0, limit - used)
    return {
        "limit": limit,
        "used": used,
        "remaining": remaining,
        "exhausted_message": settings["exhausted_message"],
        "whatsapp_number": settings["whatsapp_number"],
    }
