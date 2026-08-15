"""Timeline listing and aggregate progress stats."""
from datetime import datetime, timezone

from fastapi import APIRouter

from models.database import db
from utils.deps import CurrentUser
from utils.constants import DEFAULT_NOISE_FLOOR
from services import sessions as sessions_service

router = APIRouter(tags=["timeline"])


@router.get("/timeline")
async def timeline(user: CurrentUser):
    sessions = await db.tracking_sessions.find({"user_id": user["user_id"]}, {"_id": 0}).sort("date", 1).to_list(1000)
    return await sessions_service.attach_children(sessions)


@router.get("/progress")
async def progress(user: CurrentUser):
    sessions = await db.tracking_sessions.find({"user_id": user["user_id"]}, {"_id": 0}).sort("date", 1).to_list(1000)
    points = []
    for s in sessions:
        a = await db.analysis.find_one({"tracking_session_id": s["id"]}, {"_id": 0})
        if a:
            _dt = datetime.fromisoformat(s["date"]) if isinstance(s["date"], str) else s["date"]
            points.append({
                "label": _dt.strftime("%b %d"),
                "date": s["date"],
                "density": a["density_score"],
                "coverage": a["coverage_score"],
                "hairline": a.get("hairline_score"),
                "quality": a.get("quality_score", 0),
                "overall": a["overall_score"],
                "spread": a.get("measurement_spread"),
            })
    # Trailing 2-point rolling average of "overall", so the trend chart can offer a
    # smoothed line alongside the raw one -- a single point's noise washes out less
    # when it's not the only thing on screen.
    for i, p in enumerate(points):
        window = points[max(0, i - 1):i + 1]
        p["overall_smoothed"] = round(sum(w["overall"] for w in window) / len(window), 1)

    latest = points[-1] if points else None
    baseline = points[0] if points else None
    streak = len(sessions)
    noise_floor = (latest.get("spread") if latest else None)
    noise_floor = noise_floor if noise_floor is not None else DEFAULT_NOISE_FLOOR
    est_progress = None
    if latest and baseline and latest != baseline:
        def _delta(key):
            l, b = latest.get(key), baseline.get(key)
            return round(l - b, 1) if l is not None and b is not None else None
        est_progress = {
            "density": _delta("density"),
            "coverage": _delta("coverage"),
            "hairline": _delta("hairline"),
            "overall": _delta("overall"),
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
        "noise_floor": noise_floor,
        "last_date": last_date,
        "days_since_last": days_since,
        "total_uploads": await db.images.count_documents({"user_id": user["user_id"]}),
    }
