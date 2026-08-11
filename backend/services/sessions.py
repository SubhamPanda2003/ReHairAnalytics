"""Tracking-session domain logic: creation, hydration, and score analysis."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from . import ai_service
from models.database import db

METRIC_KEYS = [
    "hairline_score", "density_score", "coverage_score", "overall_score",
    "confidence", "quality_score", "visible_scalp_pct", "hair_coverage_pct",
]
DELTA_KEYS = ("density", "coverage", "hairline", "overall")
BLUR_QUALITY_MIN = 40

# Auto-scan frames carry a `region` (front/left/right/crown/hairline/back); manual
# uploads carry a `view` (front/top/left/right/back) instead -- present order for
# whichever tag is available.
REGION_ORDER = ["front", "left", "right", "crown", "hairline", "back", "top"]


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def get_or_create_today_session(user_id: str, notes: str = "") -> dict:
    day = today_str()
    existing = await db.tracking_sessions.find_one({"user_id": user_id, "day": day}, {"_id": 0})
    if existing:
        return existing
    count = await db.tracking_sessions.count_documents({"user_id": user_id})
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "week_number": count,
        "day": day,
        "date": datetime.now(timezone.utc).isoformat(),
        "notes": notes or "",
        "analyzed": False,
    }
    await db.tracking_sessions.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def best_image_path(session_id: str) -> Optional[str]:
    imgs = await db.images.find({"tracking_session_id": session_id}, {"_id": 0}).to_list(200)
    if not imgs:
        return None
    imgs.sort(key=lambda i: (i.get("confidence", 0), i.get("quality_score", 0)), reverse=True)
    return imgs[0].get("storage_path")


def best_per_region(images: list[dict]) -> dict:
    """Best photo (highest confidence, then quality) per region/view tag."""
    best: dict[str, dict] = {}
    for img in images:
        key = img.get("region") or img.get("view") or "photo"
        current = best.get(key)
        rank = (img.get("confidence", 0), img.get("quality_score", 0))
        if not current or rank > (current.get("confidence", 0), current.get("quality_score", 0)):
            best[key] = img
    return best


async def get_baseline_session_id(user_id: str) -> Optional[str]:
    first = await db.tracking_sessions.find({"user_id": user_id}, {"_id": 0, "id": 1}).sort("week_number", 1).to_list(1)
    return first[0]["id"] if first else None


async def attach_children(sessions: list[dict]) -> list[dict]:
    """Hydrate each tracking session with its images and analysis in bulk."""
    ids = [s["id"] for s in sessions]
    if not ids:
        return sessions
    imgs = await db.images.find({"tracking_session_id": {"$in": ids}}, {"_id": 0}).to_list(20000)
    analyses = await db.analysis.find({"tracking_session_id": {"$in": ids}}, {"_id": 0}).to_list(2000)
    img_map: dict[str, list[dict]] = {}
    for im in imgs:
        img_map.setdefault(im["tracking_session_id"], []).append(im)
    ana_map = {a["tracking_session_id"]: a for a in analyses}
    for s in sessions:
        s["images"] = img_map.get(s["id"], [])
        s["analysis"] = ana_map.get(s["id"])
    return sessions


async def get_comparison_context(user_id: str, session_id: str) -> dict:
    """Baseline/previous analysis + best image, relative to session_id, for the session detail view."""
    all_sessions = await db.tracking_sessions.find({"user_id": user_id}, {"_id": 0}).sort("week_number", 1).to_list(1000)
    previous = None
    baseline = None
    previous_best = None
    baseline_best = None
    if all_sessions:
        baseline_id = all_sessions[0]["id"]
        baseline = await db.analysis.find_one({"tracking_session_id": baseline_id}, {"_id": 0})
        baseline_best = await best_image_path(baseline_id)
        idx = next((i for i, x in enumerate(all_sessions) if x["id"] == session_id), 0)
        if idx > 0:
            previous = await db.analysis.find_one({"tracking_session_id": all_sessions[idx - 1]["id"]}, {"_id": 0})
            previous_best = await best_image_path(all_sessions[idx - 1]["id"])
    is_baseline = bool(baseline and baseline.get("tracking_session_id") == session_id)
    return {
        "previous_analysis": previous,
        "previous_best_image": previous_best,
        "baseline_analysis": None if is_baseline else baseline,
        "baseline_best_image": None if is_baseline else baseline_best,
    }


async def get_baseline_and_previous(user_id: str, session_id: str):
    """Return (baseline_analysis, previous_analysis) relative to session_id in the user's timeline."""
    all_sessions = await db.tracking_sessions.find({"user_id": user_id}, {"_id": 0}).sort("week_number", 1).to_list(1000)
    baseline_id = all_sessions[0]["id"] if all_sessions else session_id
    baseline = await db.analysis.find_one({"tracking_session_id": baseline_id}, {"_id": 0})
    idx = next((i for i, x in enumerate(all_sessions) if x["id"] == session_id), 0)
    previous = None
    if idx > 0:
        previous = await db.analysis.find_one({"tracking_session_id": all_sessions[idx - 1]["id"]}, {"_id": 0})
    return baseline, previous


def compute_deltas(current: dict, reference: Optional[dict]) -> Optional[dict]:
    if not reference:
        return None
    return {
        "density": round(current["density_score"] - reference["density_score"], 1),
        "coverage": round(current["coverage_score"] - reference["coverage_score"], 1),
        "hairline": round(current["hairline_score"] - reference["hairline_score"], 1),
        "overall": round(current["overall_score"] - reference["overall_score"], 1),
    }


async def finalize_day_analysis(user: dict, session_id: str, region: str) -> dict:
    """Aggregate every analyzed frame captured today into a single analysis document."""
    frames = await db.images.find(
        {"tracking_session_id": session_id, "confidence": {"$exists": True}}, {"_id": 0}
    ).to_list(300)
    if not frames:
        raise HTTPException(status_code=400, detail="No analyzable frames")
    usable = [f for f in frames if f.get("quality_score", 0) >= BLUR_QUALITY_MIN] or frames

    # Group usable frames by their captured (sub-)region.
    by_region: dict[str, list[dict]] = {}
    for f in usable:
        by_region.setdefault(f.get("region", region), []).append(f)

    per_region = {}
    if len(by_region) <= 1:
        # Single region (crown / hairline / full-with-no-subtags): average the most confident frames.
        only = list(by_region.values())[0] if by_region else usable
        only = sorted(only, key=lambda x: x.get("confidence", 0), reverse=True)
        topn = only[: min(4, len(only))]
        reg_key = list(by_region.keys())[0] if by_region else region
        per_region[reg_key] = {k: int(round(sum(f.get(k, 0) for f in topn) / len(topn))) for k in METRIC_KEYS}
    else:
        # Full scan: pick the single best-confidence frame per region, then blend those.
        topn = []
        for reg, fl in by_region.items():
            best = max(fl, key=lambda x: x.get("confidence", 0))
            topn.append(best)
            per_region[reg] = {k: best.get(k, 0) for k in METRIC_KEYS}

    def avg(key: str) -> int:
        return int(round(sum(f.get(key, 0) for f in topn) / len(topn)))

    metrics = {
        "hairline_score": avg("hairline_score"),
        "density_score": avg("density_score"),
        "coverage_score": avg("coverage_score"),
        "overall_score": avg("overall_score"),
        "confidence": avg("confidence"),
        "visible_scalp_pct": avg("visible_scalp_pct"),
        "hair_coverage_pct": avg("hair_coverage_pct"),
    }

    baseline, previous = await get_baseline_and_previous(user["user_id"], session_id)
    summary = await ai_service.generate_summary(metrics, previous or {}, baseline or {}, session_id)

    doc = {
        "id": str(uuid.uuid4()),
        "tracking_session_id": session_id,
        "user_id": user["user_id"],
        **metrics,
        "quality_score": avg("quality_score"),
        "region": region,
        "per_region": per_region,
        "frames_analyzed": len(frames),
        "frames_used": len(topn),
        "ai_summary": summary,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.analysis.delete_many({"tracking_session_id": session_id})
    await db.analysis.insert_one(dict(doc))
    await db.tracking_sessions.update_one({"id": session_id}, {"$set": {"analyzed": True, "region": region}})
    doc.pop("_id", None)

    is_baseline = bool(baseline and baseline.get("tracking_session_id") == session_id)
    return {
        "session_id": session_id,
        "analysis": doc,
        "vs_previous": compute_deltas(metrics, previous),
        "vs_baseline": compute_deltas(metrics, baseline) if not is_baseline else None,
    }
