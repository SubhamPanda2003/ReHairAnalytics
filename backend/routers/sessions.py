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


@router.get("/sessions/{session_id}/density-estimate")
async def get_density_estimate(session_id: str, user: CurrentUser):
    """EXPERIMENTAL rough hairs/cm^2 reading from this session's best
    front-facing photo, returned as TWO independent, clearly separate
    estimates -- never blended into one number:

    - cv_estimate: real OpenCV computation (see image_utils.estimate_hair_density
      for exactly what this does and doesn't measure -- face-based scale
      calibration + color-cluster coverage segmentation). Its margin's
      coverage_segmentation term is adjusted per-photo by an LLM assessment
      of conditions that actually affect it (hair color, hair/scalp
      contrast, lighting) -- that call never touches the hairs/cm^2 number
      itself, only how much to trust the color-clustering step for this
      specific photo (see ai_service.assess_density_reliability).
    - llm_estimate: a separate, direct visual guess from the LLM looking at
      the same photo, with its own self-reported confidence (see
      ai_service.estimate_density_llm). This is exactly what the CV estimate
      deliberately avoids doing -- it's shown alongside the CV number,
      clearly labeled as a guess, so you can see where the two agree or
      diverge, not because it's a more-trustworthy alternative.

    No fixed confidence cutoff gates this anymore -- if a face is detected at
    all, both estimates are returned along with the real face-detection
    confidence, so you can judge reliability yourself instead of getting a
    silent reject on a borderline-but-real photo. This only 422s when no
    face was detected in ANY photo in the session, and the error lists
    exactly which photos were tried and why each one failed.
    """
    s = await db.tracking_sessions.find_one({"id": session_id, "user_id": user["user_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    images = await db.images.find({"tracking_session_id": session_id}, {"_id": 0}).to_list(200)
    if not images:
        raise HTTPException(status_code=404, detail="No photos in this session")

    by_region = sessions_service.best_per_region(images)
    candidates = [by_region[key] for key in ("front", "hairline") if key in by_region]
    seen = {c["id"] for c in candidates}
    remaining = sorted(
        (i for i in images if i["id"] not in seen),
        key=lambda i: (i.get("confidence", 0), i.get("quality_score", 0)), reverse=True,
    )
    candidates.extend(remaining)

    tried = []
    for img in candidates:
        region_label = img.get("region") or img.get("view") or "unknown"
        try:
            data, _ = await asyncio.to_thread(store.get_object, img["storage_path"])
        except Exception:
            tried.append(f"{region_label} photo — couldn't load it")
            continue
        try:
            result = await asyncio.to_thread(image_utils.estimate_hair_density, data)
        except Exception:
            tried.append(f"{region_label} photo — unexpected error processing it")
            continue
        if not result:
            tried.append(f"{region_label} photo — no face detected in frame")
            continue

        b64 = await asyncio.to_thread(image_utils.to_base64_jpeg, data)

        # Non-zero only when the straight (upright) detection attempt found
        # nothing and a rotated retry is what actually found the face -- see
        # image_utils.detect_face_calibration. Surfaced so a stored-sideways
        # photo is visible to the user, not just silently corrected.
        rotation_flags = (
            [f"This photo needed a {result['rotation']}° rotation to detect a face — it may be stored sideways"]
            if result.get("rotation") else []
        )

        cv_estimate = {
            "hairs_per_cm2": result["hairs_per_cm2"],
            "margin_pct": result["margin_pct"],
            "low": result["low"],
            "high": result["high"],
            "coverage_fraction": result["coverage_fraction"],
            "confidence": result["calibration_confidence"],
            "error_sources": result["error_sources"],
            "quality_flags": rotation_flags,
        }
        try:
            reliability = await ai_service.assess_density_reliability(b64, session_id)
            adjusted_pct, flags = sessions_service.adjusted_coverage_segmentation_error(reliability)
            sources = dict(result["error_sources"])
            sources["coverage_segmentation"] = adjusted_pct
            calib = {"confidence": result["calibration_confidence"]}
            adjusted = image_utils.density_result(result["hairs_per_cm2"], result["coverage_fraction"], calib, sources)
            cv_estimate = {
                "hairs_per_cm2": adjusted["hairs_per_cm2"],
                "margin_pct": adjusted["margin_pct"],
                "low": adjusted["low"],
                "high": adjusted["high"],
                "coverage_fraction": adjusted["coverage_fraction"],
                "confidence": adjusted["calibration_confidence"],
                "error_sources": adjusted["error_sources"],
                "quality_flags": rotation_flags + flags,
            }
        except Exception:
            pass  # keep the un-adjusted (base-margin) cv_estimate rather than losing it entirely

        try:
            llm_estimate = await ai_service.estimate_density_llm(b64, session_id)
        except Exception:
            llm_estimate = {"hairs_per_cm2": None, "confidence": 0, "reasoning": None}

        return {
            "cv_estimate": cv_estimate,
            "llm_estimate": llm_estimate,
            "source_region": region_label,
        }

    raise HTTPException(
        status_code=422,
        detail=(
            "Couldn't detect a face in any photo from this session, so there's no scale reference to "
            "measure from. Tried " + str(len(tried)) + ": " + "; ".join(tried) + ". "
            "This needs at least one clear, forward-facing shot with both eyes visible -- the 'full' "
            "auto-scan's front pose, or a manual front/hairline capture."
        ),
    )


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
    b64 = await asyncio.to_thread(image_utils.to_base64_jpeg, data)
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
