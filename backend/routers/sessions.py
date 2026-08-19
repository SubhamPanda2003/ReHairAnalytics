"""Tracking-session lifecycle: create, list, auto-scan, manual upload, analyze."""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from utils import config, image_utils
from utils.constants import BLUR_VARIANCE_MIN
from models.database import db
from utils.deps import CurrentUser
from models.schemas import SessionIn
from services import ai_service, storage as store
from services import quota as quota_service
from services import sessions as sessions_service

router = APIRouter(tags=["sessions"])


@router.get("/scan/quota")
async def get_scan_quota(user: CurrentUser):
    return await quota_service.quota_for(user)


@router.post("/sessions")
async def create_session(body: SessionIn, user: CurrentUser):
    return await sessions_service.create_tracking_session(user["user_id"], body.notes or "")


@router.get("/sessions")
async def list_sessions(user: CurrentUser):
    sessions = await db.tracking_sessions.find({"user_id": user["user_id"]}, {"_id": 0}).sort("date", 1).to_list(1000)
    return await sessions_service.attach_children(sessions)


@router.get("/sessions/last-photos")
async def get_last_photos(user: CurrentUser):
    """Best photo per region from the user's most recent scan, so a new
    capture can overlay a translucent ghost of it for pose alignment."""
    session_id, photos = await sessions_service.latest_photos_by_region(user["user_id"])
    return {"session_id": session_id, "photos": photos}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user: CurrentUser):
    s = await db.tracking_sessions.find_one({"id": session_id, "user_id": user["user_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    imgs = await db.images.find({"tracking_session_id": session_id}, {"_id": 0}).to_list(200)
    imgs.sort(key=lambda i: (i.get("confidence", 0), i.get("quality_score", 0)), reverse=True)
    s["images"] = imgs
    s["analysis"] = await db.analysis.find_one({"tracking_session_id": session_id}, {"_id": 0})
    # current_best_image is set by get_comparison_context, region-matched against
    # the baseline photo when a distinct baseline exists.
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
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    region: str = Form("full"),
    frame_regions: List[str] = Form([]),
    precision: bool = Form(False),
):
    """Accepts the captured frames and hands the actual analysis (per-frame
    LLM scoring, then finalize_day_analysis) off to a background task instead
    of awaiting it here -- a full multi-region scan makes enough sequential
    LLM calls that doing this inline was slow enough to trip the reverse
    proxy's origin timeout. The client gets session_id back immediately and
    polls GET /sessions/{id} (processing + analysis fields) for the result.
    """
    if region not in ("full", "crown", "hairline"):
        region = "full"

    limit = await quota_service.effective_limit(user)
    if limit is not None and await quota_service.scan_count(user["user_id"]) >= limit:
        settings = await quota_service.get_settings()
        raise HTTPException(status_code=403, detail={
            "code": "scan_limit_reached",
            "message": settings["exhausted_message"],
            "whatsapp_number": settings["whatsapp_number"],
        })

    session = await sessions_service.create_tracking_session(user["user_id"])
    session_id = session["id"]

    regions_in = frame_regions or []
    raw_frames: List[tuple] = []
    for i, f in enumerate(files[:36]):
        raw = await f.read()
        if not raw or len(raw) > config.MAX_UPLOAD_SIZE:
            continue
        sub = regions_in[i] if i < len(regions_in) else region
        raw_frames.append((raw, sub))
    if not raw_frames:
        raise HTTPException(status_code=400, detail="No valid frames captured")

    await db.tracking_sessions.update_one({"id": session_id}, {"$set": {"processing": True}})
    background_tasks.add_task(sessions_service.process_scan, user, session_id, region, raw_frames, precision)
    return {"session_id": session_id, "status": "processing"}


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

    # Free, deterministic reject-gate before spending an LLM call to find out
    # the same thing -- same threshold as the auto-scan path (see
    # BLUR_VARIANCE_MIN's docstring). A decode failure here (bv is None)
    # doesn't reject on its own; the LLM quality check right after still runs.
    bv = await asyncio.to_thread(image_utils.blur_variance, processed)
    if bv is not None and bv < BLUR_VARIANCE_MIN:
        return {"rejected": True, "quality_score": 0, "issues": ["Photo is too blurry to measure reliably."], "retry": True}

    b64 = await asyncio.to_thread(image_utils.to_base64_jpeg_for_scoring, processed)
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


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: CurrentUser):
    """Delete a whole scan (all its photos + analysis). Baseline isn't stored
    anywhere -- it's always recomputed as the earliest remaining session -- so
    deleting the current baseline automatically promotes the next-oldest one."""
    s = await db.tracking_sessions.find_one({"id": session_id, "user_id": user["user_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.tracking_sessions.delete_one({"id": session_id, "user_id": user["user_id"]})
    await db.images.delete_many({"tracking_session_id": session_id, "user_id": user["user_id"]})
    await db.analysis.delete_many({"tracking_session_id": session_id, "user_id": user["user_id"]})
    return {"deleted": True, "id": session_id}


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
    b64 = await asyncio.to_thread(image_utils.to_base64_jpeg_for_scoring, data)
    first_call = await ai_service.analyze_metrics(b64, primary["view"], session_id)
    first_call["quality_score"] = first_call.pop("quality")
    metrics, spread = await sessions_service.ensemble_score(b64, primary["view"], "full", session_id, first_call)

    baseline, previous = await sessions_service.get_baseline_and_previous(user["user_id"], session_id)
    visual = await sessions_service.compute_visual_context(user["user_id"], session_id, primary["storage_path"], current_bytes=data)
    summary = await ai_service.generate_summary(
        metrics, previous or {}, baseline or {}, session_id,
        current_b64=visual["current_b64"], baseline_b64=visual["baseline_b64"], heatmap_b64=visual["heatmap_b64"],
    )

    avg_quality = int(sum(i["quality_score"] for i in images) / len(images))
    doc = {
        "id": str(uuid.uuid4()),
        "tracking_session_id": session_id,
        "user_id": user["user_id"],
        **metrics,
        "quality_score": avg_quality,
        "measurement_spread": spread,
        "framing_note": visual["framing_note"],
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
