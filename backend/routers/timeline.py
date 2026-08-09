"""Timeline listing and aggregate progress stats."""
from datetime import datetime, timezone

from fastapi import APIRouter

from models.database import db
from utils.deps import CurrentUser
from services import sessions as sessions_service

router = APIRouter(tags=["timeline"])


@router.get("/timeline")
async def timeline(user: CurrentUser):
    sessions = await db.tracking_sessions.find({"user_id": user["user_id"]}, {"_id": 0}).sort("week_number", 1).to_list(1000)
    return await sessions_service.attach_children(sessions)


@router.get("/progress")
async def progress(user: CurrentUser):
    sessions = await db.tracking_sessions.find({"user_id": user["user_id"]}, {"_id": 0}).sort("week_number", 1).to_list(1000)
    points = []
    for s in sessions:
        a = await db.analysis.find_one({"tracking_session_id": s["id"]}, {"_id": 0})
        if a:
            _dt = datetime.fromisoformat(s["date"]) if isinstance(s["date"], str) else s["date"]
            points.append({
                "week": s["week_number"],
                "label": _dt.strftime("%b %d"),
                "date": s["date"],
                "density": a["density_score"],
                "coverage": a["coverage_score"],
                "hairline": a["hairline_score"],
                "quality": a.get("quality_score", 0),
                "overall": a["overall_score"],
            })
    latest = points[-1] if points else None
    baseline = points[0] if points else None
    streak = len(sessions)
    est_progress = None
    if latest and baseline and latest != baseline:
        est_progress = {
            "density": round(latest["density"] - baseline["density"], 1),
            "coverage": round(latest["coverage"] - baseline["coverage"], 1),
            "hairline": round(latest["hairline"] - baseline["hairline"], 1),
            "overall": round(latest["overall"] - baseline["overall"], 1),
        }
    last_date = sessions[-1]["date"] if sessions else None
    days_since = None
    if last_date:
        ld = datetime.fromisoformat(last_date)
        if ld.tzinfo is None:
            ld = ld.replace(tzinfo=timezone.utc)
        days_since = (datetime.now(timezone.utc) - ld).days
    return {
        "points": points,
        "latest": latest,
        "baseline": baseline,
        "streak": streak,
        "estimated_progress": est_progress,
        "last_date": last_date,
        "days_since_last": days_since,
        "total_uploads": await db.images.count_documents({"user_id": user["user_id"]}),
    }
