"""Scan-credit quota: global default limit + per-user overrides, and the
configurable message shown once a user runs out.

A "scan" and a "credit" aren't 1:1 -- a precision scan (extra ensemble
re-reads + reference-photo calibration, see routers.sessions.auto_scan)
costs more than a normal one. scan_count() is the raw number of
reports/scans generated (what admins see as "reports"); credits_used() is
what actually gets charged against a user's limit."""
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

SCAN_CREDIT_COST = 1
PRECISION_SCAN_CREDIT_COST = 3


async def get_settings() -> dict:
    doc = await db.app_settings.find_one({"key": SETTINGS_ID}, {"_id": 0}) or {}
    return {**DEFAULT_SETTINGS, **doc}


async def update_settings(patch: dict) -> dict:
    if patch:
        await db.app_settings.update_one({"key": SETTINGS_ID}, {"$set": patch}, upsert=True)
    return await get_settings()


async def scan_count(user_id: str) -> int:
    """Raw number of scans/reports generated -- NOT what's charged against
    the limit once precision scans cost more than a normal one (see
    credits_used)."""
    return await db.tracking_sessions.count_documents({"user_id": user_id})


async def credits_used(user_id: str, since: Optional[str] = None) -> int:
    """Credits charged since `since` (an ISO timestamp), or all-time if not
    given. Summed from each session's own stored credits_used (set once, at
    scan time -- see services.sessions.create_tracking_session), not
    recomputed from the current cost constants, so a later change to
    pricing never retroactively reprices old scans. Sessions from before
    this field existed default to SCAN_CREDIT_COST -- the conservative
    reading, since there's no way to know in hindsight which of them were
    precision runs.

    `since` is a user's credits_reset_at (see admin_set_scan_limit): every
    time an admin explicitly sets or clears this user's limit, that's
    treated as a fresh grant -- usage before that point no longer counts
    against it, the same way a prepaid top-up doesn't inherit last period's
    balance. Scan history itself is never touched or deleted, only which of
    it counts toward the current limit."""
    match = {"user_id": user_id}
    if since:
        match["date"] = {"$gte": since}
    rows = await db.tracking_sessions.aggregate([
        {"$match": match},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$credits_used", SCAN_CREDIT_COST]}}}},
    ]).to_list(1)
    return rows[0]["total"] if rows else 0


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
    used = await credits_used(user["user_id"], since=user.get("credits_reset_at"))
    scans = await scan_count(user["user_id"])
    remaining = None if limit is None else max(0, limit - used)
    return {
        "limit": limit,
        "used": used,
        "scan_count": scans,
        "remaining": remaining,
        "scan_cost": SCAN_CREDIT_COST,
        "precision_scan_cost": PRECISION_SCAN_CREDIT_COST,
        "exhausted_message": settings["exhausted_message"],
        "whatsapp_number": settings["whatsapp_number"],
    }
