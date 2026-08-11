"""Tracking-session lifecycle: create, list, auto-scan, manual upload, analyze."""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from utils import config, image_utils
from models.database import db
from utils.deps import CurrentUser
from models.schemas import SessionIn
from services import ai_service, storage as store
from services import sessions as sessions_service

router = APIRouter(tags=["sessions"])


@router.post("/sessions")
async def create_session(body: SessionIn, user: CurrentUser):
    return await sessions_service.get_or_create_today_session(user["user_id"], body.notes or "")


@router.get("/sessions")
async def list_sessions(user: CurrentUser):
    sessions = await db.tracking_sessions.find({"user_id": user["user_id"]}, {"_id": 0}).sort("week_number", 1).to_list(1000)
    return await sessions_service.attach_children(sessions)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user: CurrentUser):
    s = await db.tracking_sessions.find_one({"id": session_id, "user_id": user["user_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    imgs = await db.images.find({"tracking_session_id": session_id}, {"_id": 0}).to_list(200)
    imgs.sort(key=lambda i: (i.get("confidence", 0), i.get("quality_score", 0)), reverse=True)
    s["images"] = imgs
    s["analysis"] = await db.analysis.find_one({"tracking_session_id": session_id}, {"_id": 0})
    s["current_best_image"] = imgs[0].get("storage_path") if imgs else None
    s.update(await sessions_service.get_comparison_context(user["user_id"], session_id))
    return s


@router.get("/sessions/{session_id}/change-maps")
async def get_change_maps(session_id: str, user: CurrentUser):
    """Pixel-aligns this session's photos against the baseline's, per matching
    region (front/left/right/crown/hairline/back), then returns a heatmap per
    region of where they visibly differ. Comparing same-region pairs avoids the
    nonsensical case of aligning e.g. a front photo against a crown photo. This
    is a visual change map, not a density/hair-count measurement."""
    s = await db.tracking_sessions.find_one({"id": session_id, "user_id": user["user_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    baseline_id = await sessions_service.get_baseline_session_id(user["user_id"])
    if not baseline_id or baseline_id == session_id:
        raise HTTPException(status_code=400, detail="Need at least two scans (baseline + this one) to generate change maps")

    current_images = await db.images.find({"tracking_session_id": session_id}, {"_id": 0}).to_list(200)
    baseline_images = await db.images.find({"tracking_session_id": baseline_id}, {"_id": 0}).to_list(200)
    current_by_region = sessions_service.best_per_region(current_images)
    baseline_by_region = sessions_service.best_per_region(baseline_images)

    shared_regions = [r for r in sessions_service.REGION_ORDER if r in current_by_region and r in baseline_by_region]
    for r in current_by_region:
        if r in baseline_by_region and r not in shared_regions:
            shared_regions.append(r)
    if not shared_regions:
        raise HTTPException(status_code=400, detail="No matching regions between baseline and this scan to compare")

    results = []
    for region in shared_regions:
        baseline_bytes, _ = await asyncio.to_thread(store.get_object, baseline_by_region[region]["storage_path"])
        current_bytes, _ = await asyncio.to_thread(store.get_object, current_by_region[region]["storage_path"])
        heatmap_bytes, aligned = await asyncio.to_thread(image_utils.align_and_diff, baseline_bytes, current_bytes)
        if heatmap_bytes is None:
            continue
        heatmap_path = f"{store.APP_NAME}/changemaps/{user['user_id']}/{session_id}-{region}.jpg"
        await asyncio.to_thread(store.put_object, heatmap_path, heatmap_bytes, "image/jpeg")
        results.append({"region": region, "heatmap_path": heatmap_path, "aligned": aligned})

    if not results:
        raise HTTPException(status_code=422, detail="Could not process these photos for comparison")
    return {"maps": results}


@router.post("/scan")
async def auto_scan(
    user: CurrentUser,
    files: List[UploadFile] = File(...),
    region: str = Form("full"),
    frame_regions: List[str] = Form([]),
):
    if region not in ("full", "crown", "hairline"):
        region = "full"
    session = await sessions_service.get_or_create_today_session(user["user_id"])
    session_id = session["id"]

    regions_in = frame_regions or []
    processed = []  # list of (proc, sub_region)
    for i, f in enumerate(files[:36]):
        raw = await f.read()
        if not raw or len(raw) > config.MAX_UPLOAD_SIZE:
            continue
        sub = regions_in[i] if i < len(regions_in) else region
        try:
            proc, _ = await asyncio.to_thread(image_utils.process_image, raw)
            processed.append((proc, sub))
        except Exception:
            continue
    if not processed:
        raise HTTPException(status_code=400, detail="No valid frames captured")

    sem = asyncio.Semaphore(6)

    async def analyze_one(i, proc, sub):
        async with sem:
            b64 = await asyncio.to_thread(image_utils.to_base64_jpeg, proc)
            m = await ai_service.analyze_metrics(b64, "scan", f"{session_id}-{i}", region=sub)
        return proc, sub, m

    results = await asyncio.gather(*[analyze_one(i, p, sub) for i, (p, sub) in enumerate(processed)])

    for proc, sub, m in results:
        img_id = str(uuid.uuid4())
        base = f"{store.APP_NAME}/uploads/{user['user_id']}/{img_id}"
        r1 = await asyncio.to_thread(store.put_object, f"{base}.jpg", proc, "image/jpeg")
        thumb = await asyncio.to_thread(image_utils.make_thumbnail, proc)
        await asyncio.to_thread(store.put_object, f"{base}_thumb.jpg", thumb, "image/jpeg")
        doc = {
            "id": img_id,
            "tracking_session_id": session_id,
            "user_id": user["user_id"],
            "view": "scan",
            "region": sub,
            "storage_path": r1["path"],
            "thumb_path": f"{base}_thumb.jpg",
            "quality_score": m["quality"],
            "hairline_score": m["hairline_score"],
            "density_score": m["density_score"],
            "coverage_score": m["coverage_score"],
            "overall_score": m["overall_score"],
            "confidence": m["confidence"],
            "visible_scalp_pct": m["visible_scalp_pct"],
            "hair_coverage_pct": m["hair_coverage_pct"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.images.insert_one(dict(doc))

    return await sessions_service.finalize_day_analysis(user, session_id, region)


@router.post("/sessions/{session_id}/upload")
async def upload_image(session_id: str, user: CurrentUser, file: UploadFile = File(...), view: str = Form(...)):
    s = await db.tracking_sessions.find_one({"id": session_id, "user_id": user["user_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if view not in config.MANUAL_VIEWS:
        raise HTTPException(status_code=400, detail="Invalid view")
    ext = (file.filename or "").split(".")[-1].lower()
    if ext not in config.ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only jpg, jpeg, png allowed")
    raw = await file.read()
    if len(raw) > config.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="Max size 10MB")

    processed, ctype = await asyncio.to_thread(image_utils.process_image, raw)
    thumb = await asyncio.to_thread(image_utils.make_thumbnail, processed)
    b64 = await asyncio.to_thread(image_utils.to_base64_jpeg, processed)

    quality = await ai_service.analyze_quality(b64, view, session_id)
    if quality["quality"] < config.MIN_ACCEPTABLE_QUALITY:
        return {"rejected": True, "quality_score": quality["quality"], "issues": quality["issues"], "retry": True}

    img_id = str(uuid.uuid4())
    base_path = f"{store.APP_NAME}/uploads/{user['user_id']}/{img_id}"
    img_path = f"{base_path}.jpg"
    thumb_path = f"{base_path}_thumb.jpg"
    r1 = await asyncio.to_thread(store.put_object, img_path, processed, ctype)
    await asyncio.to_thread(store.put_object, thumb_path, thumb, "image/jpeg")

    # remove existing image for this view in this session
    await db.images.delete_many({"tracking_session_id": session_id, "view": view})

    doc = {
        "id": img_id,
        "tracking_session_id": session_id,
        "user_id": user["user_id"],
        "view": view,
        "storage_path": r1["path"],
        "thumb_path": thumb_path,
        "quality_score": quality["quality"],
        "quality_issues": quality["issues"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.images.insert_one(dict(doc))
    doc.pop("_id", None)
    return {"rejected": False, **doc}


@router.delete("/images/{image_id}")
async def delete_image(image_id: str, user: CurrentUser):
    img = await db.images.find_one({"id": image_id, "user_id": user["user_id"]}, {"_id": 0})
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    await db.images.delete_one({"id": image_id, "user_id": user["user_id"]})
    return {"deleted": True, "id": image_id}


@router.post("/sessions/{session_id}/analyze")
async def analyze_session(session_id: str, user: CurrentUser):
    s = await db.tracking_sessions.find_one({"id": session_id, "user_id": user["user_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    images = await db.images.find({"tracking_session_id": session_id}, {"_id": 0}).to_list(20)
    if not images:
        raise HTTPException(status_code=400, detail="No images uploaded for this session")

    # pick primary image: prefer top, then front
    primary = next((i for i in images if i["view"] == "top"), None) or next((i for i in images if i["view"] == "front"), None) or images[0]
    data, _ = await asyncio.to_thread(store.get_object, primary["storage_path"])
    b64 = await asyncio.to_thread(image_utils.to_base64_jpeg, data)
    metrics = await ai_service.analyze_metrics(b64, primary["view"], session_id)

    baseline, previous = await sessions_service.get_baseline_and_previous(user["user_id"], session_id)
    summary = await ai_service.generate_summary(metrics, previous or {}, baseline or {}, session_id)

    avg_quality = int(sum(i["quality_score"] for i in images) / len(images))
    doc = {
        "id": str(uuid.uuid4()),
        "tracking_session_id": session_id,
        "user_id": user["user_id"],
        **metrics,
        "quality_score": avg_quality,
        "region": s.get("region", "full"),
        "ai_summary": summary,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.analysis.delete_many({"tracking_session_id": session_id})
    await db.analysis.insert_one(dict(doc))
    await db.tracking_sessions.update_one({"id": session_id}, {"$set": {"analyzed": True}})
    doc.pop("_id", None)

    has_distinct_baseline = bool(baseline and baseline.get("tracking_session_id") != session_id)
    return {
        "analysis": doc,
        "vs_previous": sessions_service.compute_deltas(metrics, previous),
        "vs_baseline": sessions_service.compute_deltas(metrics, baseline) if has_distinct_baseline else None,
    }
