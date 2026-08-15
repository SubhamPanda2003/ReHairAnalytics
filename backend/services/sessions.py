"""Tracking-session domain logic: creation, hydration, and score analysis."""
import asyncio
import base64
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from . import ai_service
from . import storage as store
from models.database import db
from utils import image_utils
from utils.constants import METRIC_KEYS, DELTA_KEYS, BLUR_QUALITY_MIN, ENSEMBLE_N, REGION_ORDER, BASELINE_BLEND_N


def _avg_hairline(frames: list[dict]):
    """Average hairline_score across only the frames that have one; None if none do."""
    vals = [f["hairline_score"] for f in frames if f.get("hairline_score") is not None]
    return int(round(sum(vals) / len(vals))) if vals else None


def _median(vals: list):
    if not vals:
        return None
    s = sorted(vals)
    return s[len(s) // 2]


async def ensemble_score(b64: str, view: str, region: str, session_id: str, first_call: dict) -> tuple[dict, Optional[int]]:
    """Re-analyze the same photo ENSEMBLE_N-1 more times and combine with an
    already-computed first result via per-metric median -- cancels out the
    per-call sampling noise of a single vision-LLM read. `first_call` must use
    the "quality_score" key (not analyze_metrics()'s raw "quality"), matching
    every other metrics dict in this module.

    Returns (merged_metrics, spread), where spread is the max-min of
    overall_score across every sample -- a direct measurement of how much this
    exact photo's score would wobble on a re-read. spread is None (not 0) when
    ensembling didn't actually run, so callers can tell "no noise" from "unmeasured".
    """
    extra = await asyncio.gather(*[
        ai_service.analyze_metrics(b64, view, f"{session_id}-ens{i}", region=region)
        for i in range(ENSEMBLE_N - 1)
    ], return_exceptions=True)
    # analyze_metrics() returns "quality"; every metrics dict elsewhere in this
    # module uses "quality_score" -- normalize so the median below doesn't
    # silently read 0 for every ensemble sample.
    samples = [first_call]
    for e in extra:
        if isinstance(e, dict):
            e = dict(e)
            e["quality_score"] = e.pop("quality", e.get("quality_score", 0))
            samples.append(e)
    if len(samples) < 2:
        return first_call, None

    merged = dict(first_call)
    for key in METRIC_KEYS:
        merged[key] = _median([s.get(key, 0) for s in samples])
    merged["hairline_score"] = _median([s["hairline_score"] for s in samples if s.get("hairline_score") is not None])

    overall_vals = [s.get("overall_score", 0) for s in samples]
    spread = max(overall_vals) - min(overall_vals)
    return merged, spread


async def _ensemble_frame(frame: dict, session_id: str) -> tuple[dict, Optional[int]]:
    """ensemble_score() for an auto-scan image doc, which already carries a
    first single-call reading in DB convention. Falls back to the frame's
    original scores (spread=None) if the photo can't be re-fetched -- this
    must never block finalizing the scan.
    """
    try:
        data, _ = await asyncio.to_thread(store.get_object, frame["storage_path"])
        b64 = await asyncio.to_thread(image_utils.to_base64_jpeg, data)
    except Exception:
        return frame, None
    region = frame.get("region") or "full"
    view = frame.get("view") or "scan"
    return await ensemble_score(b64, view, region, session_id, frame)


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


async def matched_best_images(session_a_id: str, session_b_id: str) -> dict:
    """Best photo from each session for a side-by-side comparison, picked from
    the SAME region when both sessions captured one -- comparing session A's
    front photo against session B's crown photo side-by-side would silently be
    comparing two different parts of the scalp, not progress in one place.
    Prefers "front" (present in nearly every scan mode), then whichever other
    region both sessions share, in REGION_ORDER. Falls back to each session's
    independent best-overall photo only when they share no region at all.

    Returns {"a_path": str|None, "b_path": str|None, "region": str|None,
    "matched": bool}. matched=False means the fallback ran and the pair may show
    different regions -- callers should caveat that in the UI.
    """
    imgs_a = await db.images.find({"tracking_session_id": session_a_id}, {"_id": 0}).to_list(200)
    imgs_b = await db.images.find({"tracking_session_id": session_b_id}, {"_id": 0}).to_list(200)
    by_region_a = best_per_region(imgs_a)
    by_region_b = best_per_region(imgs_b)
    shared = [r for r in REGION_ORDER if r in by_region_a and r in by_region_b]
    if shared:
        region = "front" if "front" in shared else shared[0]
        return {
            "a_path": by_region_a[region]["storage_path"],
            "b_path": by_region_b[region]["storage_path"],
            "region": region,
            "matched": True,
        }
    a_best = max(imgs_a, key=lambda i: (i.get("confidence", 0), i.get("quality_score", 0))) if imgs_a else None
    b_best = max(imgs_b, key=lambda i: (i.get("confidence", 0), i.get("quality_score", 0))) if imgs_b else None
    return {
        "a_path": a_best["storage_path"] if a_best else None,
        "b_path": b_best["storage_path"] if b_best else None,
        "region": None,
        "matched": False,
    }


async def get_baseline_session_id(user_id: str) -> Optional[str]:
    first = await db.tracking_sessions.find({"user_id": user_id}, {"_id": 0, "id": 1}).sort("week_number", 1).to_list(1)
    return first[0]["id"] if first else None


async def compute_visual_context(
    user_id: str, session_id: str, current_image_path: Optional[str], current_bytes: Optional[bytes] = None,
) -> dict:
    """Everything generate_summary() needs to give real, photo-grounded insight
    instead of only reciting score deltas: base64-encoded current/baseline
    photos, a change-map heatmap between them, and the framing-consistency
    numbers -- all from a single ORB/homography pass (image_utils.compare_photos)
    against the baseline's representative photo. Computed once at analysis time
    (not per page view); the analysis doc only stores framing_note (JSON-safe),
    the image data is used in-memory for the LLM call and discarded.

    Returns {"framing_note": dict|None, "current_b64": str|None,
    "baseline_b64": str|None, "heatmap_b64": str|None}. Degrades to fewer/no
    images on any failure (no baseline yet, storage unavailable, CV failure) --
    this must never block finalizing a scan.
    """
    result = {"framing_note": None, "current_b64": None, "baseline_b64": None, "heatmap_b64": None}
    if not current_image_path:
        return result
    try:
        if current_bytes is None:
            current_bytes, _ = await asyncio.to_thread(store.get_object, current_image_path)
        result["current_b64"] = await asyncio.to_thread(image_utils.to_base64_jpeg, current_bytes)
    except Exception:
        return result

    baseline_id = await get_baseline_session_id(user_id)
    if not baseline_id or baseline_id == session_id:
        return result
    baseline_path = await best_image_path(baseline_id)
    if not baseline_path:
        return result
    try:
        baseline_bytes, _ = await asyncio.to_thread(store.get_object, baseline_path)
        result["baseline_b64"] = await asyncio.to_thread(image_utils.to_base64_jpeg, baseline_bytes)
        cmp = await asyncio.to_thread(image_utils.compare_photos, baseline_bytes, current_bytes)
        result["framing_note"] = {
            "aligned": cmp["aligned"], "match_count": cmp["match_count"], "scale_shift_pct": cmp["scale_shift_pct"],
        }
        if cmp["heatmap_jpeg"]:
            result["heatmap_b64"] = base64.b64encode(cmp["heatmap_jpeg"]).decode()
    except Exception:
        pass
    return result


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


_BLEND_KEYS = ("density_score", "coverage_score", "overall_score", "confidence",
               "quality_score", "visible_scalp_pct", "hair_coverage_pct")


async def _blended_baseline(all_sessions: list[dict]) -> Optional[dict]:
    """Average the analysis docs of the first BASELINE_BLEND_N sessions that have
    one (tolerates an unanalyzed early session, unlike a single fixed lookup).
    Returns None if none of them do yet."""
    docs = []
    for s in all_sessions[:BASELINE_BLEND_N]:
        a = await db.analysis.find_one({"tracking_session_id": s["id"]}, {"_id": 0})
        if a:
            docs.append(a)
    if not docs:
        return None
    if len(docs) == 1:
        return docs[0]

    blended = dict(docs[0])
    for key in _BLEND_KEYS:
        vals = [d[key] for d in docs if d.get(key) is not None]
        if vals:
            blended[key] = int(round(sum(vals) / len(vals)))
    hairline_vals = [d["hairline_score"] for d in docs if d.get("hairline_score") is not None]
    blended["hairline_score"] = int(round(sum(hairline_vals) / len(hairline_vals))) if hairline_vals else None
    blended["blended_from_sessions"] = len(docs)
    return blended


async def get_comparison_context(user_id: str, session_id: str) -> dict:
    """Baseline/previous analysis + best images, relative to session_id, for the
    session detail view. When a distinct baseline exists, its photo and this
    session's photo are picked from the SAME region (see matched_best_images) so
    the side-by-side comparison shows the same part of the scalp, not whichever
    photo happened to score highest in each session independently.
    """
    all_sessions = await db.tracking_sessions.find({"user_id": user_id}, {"_id": 0}).sort("week_number", 1).to_list(1000)
    if not all_sessions:
        return {
            "previous_analysis": None, "previous_best_image": None,
            "baseline_analysis": None, "baseline_best_image": None,
            "current_best_image": None, "photo_comparison_region_matched": None,
        }

    baseline_id = all_sessions[0]["id"]
    is_baseline = baseline_id == session_id
    idx = next((i for i, x in enumerate(all_sessions) if x["id"] == session_id), 0)

    previous = None
    previous_best = None
    if idx > 0:
        previous = await db.analysis.find_one({"tracking_session_id": all_sessions[idx - 1]["id"]}, {"_id": 0})
        previous_best = await best_image_path(all_sessions[idx - 1]["id"])

    if is_baseline:
        return {
            "previous_analysis": previous,
            "previous_best_image": previous_best,
            "baseline_analysis": None,
            "baseline_best_image": None,
            "current_best_image": await best_image_path(session_id),
            "photo_comparison_region_matched": None,
        }

    baseline = await _blended_baseline(all_sessions)
    matched = await matched_best_images(baseline_id, session_id)
    return {
        "previous_analysis": previous,
        "previous_best_image": previous_best,
        "baseline_analysis": baseline,
        "baseline_best_image": matched["a_path"],
        "current_best_image": matched["b_path"],
        "photo_comparison_region_matched": matched["matched"],
    }


async def get_baseline_and_previous(user_id: str, session_id: str):
    """Return (baseline_analysis, previous_analysis) relative to session_id in the user's timeline."""
    all_sessions = await db.tracking_sessions.find({"user_id": user_id}, {"_id": 0}).sort("week_number", 1).to_list(1000)
    baseline = await _blended_baseline(all_sessions) if all_sessions else None
    idx = next((i for i, x in enumerate(all_sessions) if x["id"] == session_id), 0)
    previous = None
    if idx > 0:
        previous = await db.analysis.find_one({"tracking_session_id": all_sessions[idx - 1]["id"]}, {"_id": 0})
    return baseline, previous


def compute_deltas(current: dict, reference: Optional[dict]) -> Optional[dict]:
    if not reference:
        return None

    def d(key: str):
        c, r = current.get(key), reference.get(key)
        return round(c - r, 1) if c is not None and r is not None else None

    return {
        "density": d("density_score"),
        "coverage": d("coverage_score"),
        "hairline": d("hairline_score"),
        "overall": d("overall_score"),
    }


async def _compute_density_estimate(images: list[dict], session_id: str) -> Optional[dict]:
    """Rough hairs/cm^2 guess from the LLM (see ai_service.estimate_density_llm),
    computed ONCE per scan here and stored on the analysis document -- not
    re-queried (and not re-billed) every time the UI panel showing it gets
    opened. Picks the same photo the old on-demand endpoint preferred (front,
    then hairline, then best overall). Returns None on any failure -- this is
    an optional, experimental figure and must never block the rest of the
    scan's analysis from saving.
    """
    by_region = best_per_region(images)
    candidate = next((by_region[k] for k in ("front", "hairline") if k in by_region), None)
    if candidate is None and images:
        candidate = max(images, key=lambda i: (i.get("confidence", 0), i.get("quality_score", 0)))
    if candidate is None:
        return None
    try:
        data, _ = await asyncio.to_thread(store.get_object, candidate["storage_path"])
        b64 = await asyncio.to_thread(image_utils.to_base64_jpeg, data)
        result = await ai_service.estimate_density_llm(b64, session_id)
    except Exception:
        return None
    if result.get("hairs_per_cm2") is None:
        return None
    result["source_region"] = candidate.get("region") or candidate.get("view") or "unknown"
    return result


async def _generate_scalp_map(storage_path: str, user_id: str, session_id: str, region: str) -> Optional[str]:
    """Color-based visual highlight of scalp-colored patches in one region's
    representative photo (see image_utils.mark_scalp_patches) -- a visual aid,
    not a measurement. Returns the stored overlay image's path, or None if the
    source photo can't be loaded or processed; never blocks the rest of the
    scan's analysis from saving.
    """
    try:
        data, _ = await asyncio.to_thread(store.get_object, storage_path)
        overlay = await asyncio.to_thread(image_utils.mark_scalp_patches, data)
    except Exception:
        return None
    if overlay is None:
        return None
    path = f"{store.APP_NAME}/scalpmaps/{user_id}/{session_id}-{region}.jpg"
    await asyncio.to_thread(store.put_object, path, overlay, "image/jpeg")
    return path


async def _region_insights(
    per_region: dict, region_storage_path: dict, baseline: Optional[dict], previous: Optional[dict], session_id: str,
) -> Optional[dict]:
    """Region-by-region AI insight (see ai_service.generate_region_insights) --
    only worth the extra call when there's more than one region to break out;
    a single-region scan's breakdown would just repeat the overall ai_summary.
    Returns None on failure or when there's nothing to break out; never blocks
    the rest of the scan's analysis from saving.
    """
    if len(per_region) <= 1:
        return None
    previous_per_region = (previous or {}).get("per_region") or {}
    baseline_per_region = (baseline or {}).get("per_region") or {}
    regions_payload = {}
    for reg, m in per_region.items():
        image_b64 = None
        sp = region_storage_path.get(reg)
        if sp:
            try:
                data, _ = await asyncio.to_thread(store.get_object, sp)
                image_b64 = await asyncio.to_thread(image_utils.to_base64_jpeg, data)
            except Exception:
                image_b64 = None
        regions_payload[reg] = {
            "current": m,
            "previous": previous_per_region.get(reg),
            "baseline": baseline_per_region.get(reg),
            "image_b64": image_b64,
        }
    try:
        return await ai_service.generate_region_insights(regions_payload, session_id)
    except Exception:
        return None


async def finalize_day_analysis(user: dict, session_id: str, region: str, precision: bool = False) -> dict:
    """Aggregate every analyzed frame captured today into a single analysis
    document. `precision` gates the ensemble re-analysis step below (see
    _ensemble_frame/ensemble_score) -- on, each region's winning frame gets
    re-read ENSEMBLE_N-1 more times and the results combined to cancel out
    per-call scoring noise; off, it's scored from the single existing read,
    which is faster and cheaper but more exposed to a given call's noise.
    """
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
    region_spreads: list[int] = []
    region_storage_path: dict[str, str] = {}
    if len(by_region) <= 1:
        # Single region (crown / hairline / full-with-no-subtags): average the most confident frames.
        only = list(by_region.values())[0] if by_region else usable
        only = sorted(only, key=lambda x: x.get("confidence", 0), reverse=True)
        topn = only[: min(4, len(only))]
        reg_key = list(by_region.keys())[0] if by_region else region
        reg_metrics = {k: int(round(sum(f.get(k, 0) for f in topn) / len(topn))) for k in METRIC_KEYS}
        hairline = _avg_hairline(topn)
        if hairline is not None:
            reg_metrics["hairline_score"] = hairline
        # No extra LLM calls here (already-blended frames are its own noise-reduction
        # step) -- but the spread across the frames captured this session is a free,
        # real signal, so use it instead of re-analyzing.
        if len(topn) >= 2:
            overall_vals = [f.get("overall_score", 0) for f in topn]
            reg_metrics["spread"] = max(overall_vals) - min(overall_vals)
            region_spreads.append(reg_metrics["spread"])
        region_storage_path[reg_key] = topn[0]["storage_path"]
        reg_metrics["scalp_map_path"] = await _generate_scalp_map(topn[0]["storage_path"], user["user_id"], session_id, reg_key)
        per_region[reg_key] = reg_metrics
    else:
        # Full scan: pick the single best-confidence frame per region, ensemble-reanalyze
        # just that one frame a few times to cancel out per-call noise, then blend those.
        topn = []
        for reg, fl in by_region.items():
            best = max(fl, key=lambda x: x.get("confidence", 0))
            ensembled, spread = await _ensemble_frame(best, session_id) if precision else (best, None)
            topn.append(ensembled)
            reg_metrics = {k: ensembled.get(k, 0) for k in METRIC_KEYS}
            if ensembled.get("hairline_score") is not None:
                reg_metrics["hairline_score"] = ensembled["hairline_score"]
            if spread is not None:
                reg_metrics["spread"] = spread
                region_spreads.append(spread)
            region_storage_path[reg] = best["storage_path"]
            reg_metrics["scalp_map_path"] = await _generate_scalp_map(best["storage_path"], user["user_id"], session_id, reg)
            per_region[reg] = reg_metrics

    def avg(key: str) -> int:
        return int(round(sum(f.get(key, 0) for f in topn) / len(topn)))

    # Empirical, per-scan noise floor: how much would this session's own overall_score
    # plausibly wobble on a re-read. None (not 0) when we have no basis to estimate it,
    # so callers can fall back to a documented default rather than trusting a false "0".
    measurement_spread = int(round(sum(region_spreads) / len(region_spreads))) if region_spreads else None

    metrics = {
        "hairline_score": _avg_hairline(topn),
        "density_score": avg("density_score"),
        "coverage_score": avg("coverage_score"),
        "overall_score": avg("overall_score"),
        "confidence": avg("confidence"),
        "visible_scalp_pct": avg("visible_scalp_pct"),
        "hair_coverage_pct": avg("hair_coverage_pct"),
    }

    baseline, previous = await get_baseline_and_previous(user["user_id"], session_id)
    current_best = await best_image_path(session_id)
    visual = await compute_visual_context(user["user_id"], session_id, current_best)
    summary = await ai_service.generate_summary(
        metrics, previous or {}, baseline or {}, session_id,
        current_b64=visual["current_b64"], baseline_b64=visual["baseline_b64"], heatmap_b64=visual["heatmap_b64"],
    )
    density_estimate = await _compute_density_estimate(frames, session_id)
    region_insights = await _region_insights(per_region, region_storage_path, baseline, previous, session_id)

    doc = {
        "id": str(uuid.uuid4()),
        "tracking_session_id": session_id,
        "user_id": user["user_id"],
        **metrics,
        "quality_score": avg("quality_score"),
        "region": region,
        "per_region": per_region,
        "measurement_spread": measurement_spread,
        "framing_note": visual["framing_note"],
        "frames_analyzed": len(frames),
        "frames_used": len(topn),
        "ai_summary": summary,
        "region_insights": region_insights,
        "density_estimate": density_estimate,
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
