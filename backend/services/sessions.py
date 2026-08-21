"""Tracking-session domain logic: creation, hydration, and score analysis."""
import asyncio
import base64
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from . import ai_service
from . import storage as store
from models.database import db
from utils import image_utils
from utils.constants import (
    METRIC_KEYS, DELTA_KEYS, BLUR_QUALITY_MIN, ENSEMBLE_N, REGION_ORDER, BASELINE_BLEND_N, LLM_FAILURE_SENTINEL,
    CAPTURE_NOISE_FLOOR, BLUR_VARIANCE_MIN,
)
from utils.trend import combined_noise_floor, fit_trend

logger = logging.getLogger(__name__)


def _avg_hairline(frames: list[dict]):
    """Average hairline_score across frames where it's APPLICABLE (not None,
    e.g. excludes crown/back frames) -- distinct from whether it's a real
    reading. Real (non-sentinel) values are preferred and averaged together;
    only when hairline was applicable everywhere it appears but every single
    one of those calls failed does this return LLM_FAILURE_SENTINEL itself,
    so a genuine failure stays a visible -1 instead of silently collapsing
    into the same None used for "not applicable at all" -- a region-winning
    frame whose hairline call failed must still show up as a failure, not
    quietly vanish as if hairline weren't in frame. Returns None only when
    no frame in the list says hairline is applicable to begin with."""
    applicable = [v for v in (f.get("hairline_score") for f in frames) if v is not None]
    if not applicable:
        return None
    real = [v for v in applicable if v != LLM_FAILURE_SENTINEL]
    if not real:
        return LLM_FAILURE_SENTINEL
    return int(round(sum(real) / len(real)))


def _median(vals: list):
    if not vals:
        return None
    s = sorted(vals)
    return s[len(s) // 2]


def _avg_real(frames: list[dict], key: str) -> int:
    """Average `key` across frames, skipping LLM_FAILURE_SENTINEL entries so
    one failed call doesn't drag a real average toward a fabricated-looking
    number. Returns LLM_FAILURE_SENTINEL itself if every frame failed for
    this key -- an honest "no data", not a fake one."""
    vals = [v for v in (f.get(key, LLM_FAILURE_SENTINEL) for f in frames) if v != LLM_FAILURE_SENTINEL]
    return int(round(sum(vals) / len(vals))) if vals else LLM_FAILURE_SENTINEL


def _spread_to_confidence(spread: int) -> int:
    """Derived reliability signal from ensemble spread (how much repeated
    reads of the SAME photo disagree) instead of the model's own
    self-reported confidence. A 42-photo real-Gemini test found self-reported
    confidence clustered at 90/95/100 regardless of actual reliability -- it
    didn't even drop on the one read with a wild internal density/coverage
    disagreement (75 vs 15, confidence=95). Spread is an empirical
    measurement, not a self-assessment, so it discriminates where
    self-reported confidence doesn't -- though this specific linear mapping
    is a reasonable starting point, not a fitted/validated curve."""
    return max(0, min(100, round(100 - spread * 2.5)))


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

    # A sample whose overall_score is the failure sentinel means that whole
    # re-read failed -- drop it rather than blending a known-bad reading into
    # the median/spread alongside real ones. If the very first read is what
    # failed but a re-read succeeded, this also lets a real sample win instead
    # of permanently locking in the failure.
    real_samples = [s for s in samples if s.get("overall_score") != LLM_FAILURE_SENTINEL]
    if len(real_samples) < 2:
        return (real_samples[0] if real_samples else first_call), None

    merged = dict(real_samples[0])
    for key in METRIC_KEYS:
        vals = [v for v in (s.get(key, LLM_FAILURE_SENTINEL) for s in real_samples) if v != LLM_FAILURE_SENTINEL]
        merged[key] = _median(vals) if vals else LLM_FAILURE_SENTINEL
    if first_call.get("hairline_score") is None:
        merged["hairline_score"] = None  # not applicable to this region at all
    else:
        hairline_vals = [s["hairline_score"] for s in real_samples if s.get("hairline_score") not in (None, LLM_FAILURE_SENTINEL)]
        merged["hairline_score"] = _median(hairline_vals) if hairline_vals else LLM_FAILURE_SENTINEL

    overall_vals = [s.get("overall_score", 0) for s in real_samples]
    spread = max(overall_vals) - min(overall_vals)
    merged["confidence"] = _spread_to_confidence(spread)
    return merged, spread


async def _previous_region_reference(previous: Optional[dict], region: str) -> tuple[Optional[bytes], Optional[dict]]:
    """Same-region photo (raw bytes) + score from the user's immediately-
    preceding analyzed session -- used both for ai_service.analyze_metrics's
    reference_b64/reference_score (calibrating the numeric scale week over
    week) and, when the match is confident enough, for aligning the current
    photo's framing against it (see image_utils.align_to_reference) before
    either gets scored. Returns raw bytes, not base64 -- callers decide when
    to lighting-normalize/encode, since alignment needs to run on raw pixels
    first. Returns (None, None) when there's no previous session or it never
    scored this exact region -- must never block scoring the current frame.
    """
    if not previous:
        return None, None
    score = (previous.get("per_region") or {}).get(region)
    if score is None:
        return None, None
    image_bytes = None
    prev_session_id = previous.get("tracking_session_id")
    if prev_session_id:
        try:
            imgs = await db.images.find({"tracking_session_id": prev_session_id, "region": region}, {"_id": 0}).to_list(50)
            if imgs:
                best = max(imgs, key=lambda i: (i.get("confidence", 0), i.get("quality_score", 0)))
                image_bytes, _ = await asyncio.to_thread(store.get_object, best["storage_path"])
        except Exception:
            image_bytes = None
    return image_bytes, score


async def _reference_scored_frame(storage_path: str, view: str, region: str, session_id: str, previous: Optional[dict]) -> Optional[dict]:
    """One extra analyze_metrics() read of a region's winning photo, given the
    previous session's same-region photo+score as a calibration reference.
    Folded into the SAME median/average as that region's other reads rather
    than replacing them -- a reference-conditioned read is no longer a fully
    independent sample, so it should moderate the final score, not dictate it.

    Before scoring, the current photo is aligned to the reference's framing
    (image_utils.align_to_reference, falls back to the raw photo when the
    match isn't confident) and both photos are lighting-normalized -- the
    reference-scoring call site is a natural place for this since it's
    already fetching both photos for comparison.

    Returns None (skip) when there's no usable previous reference or on any
    failure -- must never block finalizing the scan."""
    ref_bytes, ref_score = await _previous_region_reference(previous, region)
    if ref_score is None:
        return None
    try:
        data, _ = await asyncio.to_thread(store.get_object, storage_path)
        if ref_bytes is not None:
            data, _aligned = await asyncio.to_thread(image_utils.align_to_reference, ref_bytes, data)
        b64 = await asyncio.to_thread(image_utils.to_base64_jpeg_for_scoring, data)
        ref_b64 = await asyncio.to_thread(image_utils.to_base64_jpeg_for_scoring, ref_bytes) if ref_bytes is not None else None
        result = await ai_service.analyze_metrics(
            b64, view, f"{session_id}-{region}-ref", region=region,
            reference_b64=ref_b64, reference_score=ref_score,
        )
    except Exception:
        return None
    if result.get("overall_score") == LLM_FAILURE_SENTINEL:
        return None
    result = dict(result)
    result["quality_score"] = result.pop("quality", result.get("quality_score", 0))
    return result


async def _ensemble_frame(frame: dict, session_id: str) -> tuple[dict, Optional[int]]:
    """ensemble_score() for an auto-scan image doc, which already carries a
    first single-call reading in DB convention. Falls back to the frame's
    original scores (spread=None) if the photo can't be re-fetched -- this
    must never block finalizing the scan.
    """
    try:
        data, _ = await asyncio.to_thread(store.get_object, frame["storage_path"])
        b64 = await asyncio.to_thread(image_utils.to_base64_jpeg_for_scoring, data)
    except Exception:
        return frame, None
    region = frame.get("region") or "full"
    view = frame.get("view") or "scan"
    return await ensemble_score(b64, view, region, session_id, frame)


async def create_tracking_session(user_id: str, notes: str = "", precision: bool = False, credits_used: int = 1) -> dict:
    """Every call creates its own session, identified by a precise timestamp
    (not just a calendar date) -- so scanning again later today doesn't get
    silently merged into this morning's session, and multiple scans on the
    same day show up as distinct, independently viewable results.

    credits_used is stamped on the session at creation time (the caller
    already knows the cost -- see routers.sessions.auto_scan) and is what
    services.quota.credits_used later sums per user; storing it here rather
    than recomputing it from `precision` later means a future change to the
    cost constants can't silently reprice a scan after the fact.
    """
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "date": datetime.now(timezone.utc).isoformat(),
        "notes": notes or "",
        "analyzed": False,
        "processing": False,
        "precision": precision,
        "credits_used": credits_used,
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


async def build_progress(user_id: str) -> dict:
    """Score-trend summary for one user -- same shape whether it's the user
    viewing their own /progress or a dermatologist viewing a shared patient
    history (see routers/appointments.py's /history, gated on consent)."""
    sessions = await db.tracking_sessions.find({"user_id": user_id}, {"_id": 0}).sort("date", 1).to_list(1000)
    points = []
    for s in sessions:
        a = await db.analysis.find_one({"tracking_session_id": s["id"]}, {"_id": 0})
        if a:
            _dt = datetime.fromisoformat(s["date"]) if isinstance(s["date"], str) else s["date"]
            framing_note = a.get("framing_note")
            points.append({
                "label": _dt.strftime("%b %d"),
                "date": s["date"],
                "density": a["density_score"],
                "coverage": a["coverage_score"],
                "hairline": a.get("hairline_score"),
                "quality": a.get("quality_score", 0),
                "overall": a["overall_score"],
                "spread": a.get("measurement_spread"),
                # None for the baseline session itself (nothing to align
                # against yet), else whether this photo's ORB/homography
                # alignment against the baseline actually succeeded -- a
                # real input to how much a delta involving this point should
                # be trusted, not just the AI's own score confidence.
                "framing_ok": framing_note.get("aligned") if framing_note else None,
            })
    for i, p in enumerate(points):
        window = points[max(0, i - 1):i + 1]
        p["overall_smoothed"] = round(sum(w["overall"] for w in window) / len(window), 1)

    latest = points[-1] if points else None
    baseline = points[0] if points else None
    streak = len(sessions)
    # Rounded before it ever leaves this function -- root-sum-square combining
    # a whole-number constant with a real measured spread produces something
    # like 17.11724276..., and every caller (Report's "changes smaller than
    # ±X points" copy included) would otherwise display that raw float
    # verbatim. That's false precision: CAPTURE_NOISE_FLOOR itself is a loose,
    # n=3 estimate (see its docstring), so a 4-decimal-place noise floor
    # doesn't mean anything the way a lab measurement's would.
    noise_floor = round(combined_noise_floor(CAPTURE_NOISE_FLOOR, latest.get("spread") if latest else None), 1)
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

    # Whether the OVERALL score is really trending, not just wobbling within
    # noise -- fits a line across every point (not just latest-vs-baseline)
    # and only calls it "confirmed" once the slope clears a threshold set by
    # REAL measured noise (see utils/trend.py), not an assumed one.
    trend = fit_trend(points, "overall", noise_floor)
    misaligned = [p for p in points if p.get("framing_ok") is False]
    if trend["confirmed"] and misaligned:
        # A statistically clean slope doesn't mean much if some of the
        # photos it's built on didn't actually align with the baseline --
        # framing drift can produce a fake trend just as easily as it can
        # hide a real one. Veto rather than silently average it in.
        trend["confirmed"] = False
        trend["caveat"] = (
            f"{len(misaligned)} photo(s) in this range didn't align well with the baseline -- "
            "treating the trend as unconfirmed until framing is more consistent."
        )

    return {
        "points": points,
        "latest": latest,
        "baseline": baseline,
        "streak": streak,
        "estimated_progress": est_progress,
        "noise_floor": noise_floor,
        "trend": trend,
        "last_date": last_date,
        "days_since_last": days_since,
        "total_uploads": await db.images.count_documents({"user_id": user_id}),
    }


async def latest_photos_by_region(user_id: str) -> tuple:
    """(session_id, {region: thumb_path}) for a user's most recent scan --
    used both for the new-scan ghost-overlay alignment guide and for the
    photos shown in a dermatologist's shared patient-history view."""
    last = await db.tracking_sessions.find({"user_id": user_id}, {"_id": 0}).sort("date", -1).to_list(1)
    if not last:
        return None, {}
    session_id = last[0]["id"]
    imgs = await db.images.find({"tracking_session_id": session_id, "user_id": user_id}, {"_id": 0}).to_list(200)
    by_region = best_per_region(imgs)
    return session_id, {region: img["thumb_path"] for region, img in by_region.items()}


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
    first = await db.tracking_sessions.find({"user_id": user_id}, {"_id": 0, "id": 1}).sort("date", 1).to_list(1)
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
        vals = [d[key] for d in docs if d.get(key) is not None and d.get(key) != LLM_FAILURE_SENTINEL]
        if vals:
            blended[key] = int(round(sum(vals) / len(vals)))
    hairline_vals = [d["hairline_score"] for d in docs if d.get("hairline_score") is not None and d.get("hairline_score") != LLM_FAILURE_SENTINEL]
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
    all_sessions = await db.tracking_sessions.find({"user_id": user_id}, {"_id": 0}).sort("date", 1).to_list(1000)
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
    all_sessions = await db.tracking_sessions.find({"user_id": user_id}, {"_id": 0}).sort("date", 1).to_list(1000)
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
        if c is None or r is None or c == LLM_FAILURE_SENTINEL or r == LLM_FAILURE_SENTINEL:
            return None
        return round(c - r, 1)

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
    opened. Prefers the crown photo -- crown/vertex is where pattern hair
    loss actually shows up densitometrically (same reasoning as the
    crown-only scalp map), and it's consistently framed with minimal
    face/neck skin in shot, unlike front. Falls back to the old priority
    (front, then hairline, then best overall) when a scan didn't capture
    crown at all (e.g. a hairline- or front-focused single-region scan), so
    this stays useful outside full/crown scans rather than going blank.
    Returns None on any failure -- this is an optional, experimental figure
    and must never block the rest of the scan's analysis from saving.
    """
    by_region = best_per_region(images)
    candidate = next((by_region[k] for k in ("crown", "front", "hairline") if k in by_region), None)
    if candidate is None and images:
        candidate = max(images, key=lambda i: (i.get("confidence", 0), i.get("quality_score", 0)))
    if candidate is None:
        return None
    try:
        data, _ = await asyncio.to_thread(store.get_object, candidate["storage_path"])
        b64 = await asyncio.to_thread(image_utils.to_base64_jpeg_for_scoring, data)
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

    Called by finalize_day_analysis ONLY for the "crown" region -- crown is
    the one view this heuristic was actually built/tuned against (also the
    source of the real photos used to validate the lighting/background
    fixes in image_utils.py), and other regions carry more of its known
    failure modes (front's face/neck skin, side views' ears/background) with
    no extra benefit. Callers should pass region="crown" and treat any other
    value as "don't call this at all" rather than relying on a check here.
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
    document. `precision` gates two extra-cost reliability steps, both applied
    only to the single winning frame per region (not every captured frame):
    ensemble re-analysis (see _ensemble_frame/ensemble_score) re-reads that
    frame ENSEMBLE_N-1 more times to cancel out per-call sampling noise, and
    reference-scored re-analysis (see _reference_scored_frame) reads it once
    more against the user's previous scan of that same region, to keep the
    numeric scale calibrated week over week. Off, a region is scored from its
    single existing read, which is faster and cheaper but more exposed to
    both kinds of noise.
    """
    frames = await db.images.find(
        {"tracking_session_id": session_id, "confidence": {"$exists": True}}, {"_id": 0}
    ).to_list(300)
    if not frames:
        raise HTTPException(status_code=400, detail="No analyzable frames")
    # A quality_score of LLM_FAILURE_SENTINEL means the quality CHECK failed --
    # that's not the same as a genuinely blurry photo, and must not be dropped
    # here the same way: a real frame quietly disappearing from its region
    # (rather than showing up with a visible failed reading) is exactly the
    # "hide the failure" problem this sentinel exists to avoid.
    usable = [
        f for f in frames
        if f.get("quality_score", 0) >= BLUR_QUALITY_MIN or f.get("quality_score") == LLM_FAILURE_SENTINEL
    ] or frames

    # Needed per-region below (to fetch each region's previous photo+score as a
    # calibration reference), not just for the top-level deltas at the end --
    # moved up from its old call site right before the doc is built.
    baseline, previous = await get_baseline_and_previous(user["user_id"], session_id)

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
        # Spread/confidence below must reflect pure CAPTURE noise -- this
        # session's own repeated frames of the same region -- computed from
        # `topn` BEFORE the reference-conditioned read is folded in. That read
        # is semi-correlated with the previous session by design (that's the
        # whole point of it), so mixing it into a max-min spread would
        # conflate "consistent with last time" with "genuinely low noise",
        # and could just as easily widen the reported spread as narrow it.
        overall_vals = [v for v in (f.get("overall_score", 0) for f in topn) if v != LLM_FAILURE_SENTINEL]
        if precision:
            # One extra read of the winning frame, calibrated against this
            # region's previous photo+score (see _reference_scored_frame) --
            # folded in alongside the other frames rather than replacing them.
            ref_frame = await _reference_scored_frame(
                topn[0]["storage_path"], topn[0].get("view") or "scan", reg_key, session_id, previous,
            )
            if ref_frame:
                topn = topn + [ref_frame]
        reg_metrics = {k: _avg_real(topn, k) for k in METRIC_KEYS}
        hairline = _avg_hairline(topn)
        if hairline is not None:
            reg_metrics["hairline_score"] = hairline
        # No extra LLM calls here (already-blended frames are its own noise-reduction
        # step) -- but the spread across the frames captured this session is a free,
        # real signal, so use it instead of re-analyzing. Only across frames that
        # actually produced a real overall_score -- a failed read isn't "spread",
        # it's missing data, and would otherwise inflate the spread artificially.
        if len(overall_vals) >= 2:
            reg_metrics["spread"] = max(overall_vals) - min(overall_vals)
            region_spreads.append(reg_metrics["spread"])
            # Same rationale as ensemble_score's override: measured spread
            # across this region's own captured frames is a real reliability
            # signal, self-reported confidence isn't.
            reg_metrics["confidence"] = _spread_to_confidence(reg_metrics["spread"])
        region_storage_path[reg_key] = topn[0]["storage_path"]
        # Scalp map is crown-only (see _generate_scalp_map's docstring) --
        # every other region gets no map generated at all, not just a hidden
        # one, so this also skips the GrabCut/k-means work for regions where
        # it was never shown.
        reg_metrics["scalp_map_path"] = await _generate_scalp_map(topn[0]["storage_path"], user["user_id"], session_id, reg_key) if reg_key == "crown" else None
        per_region[reg_key] = reg_metrics
    else:
        # Full scan: pick the single best-confidence frame per region, ensemble-reanalyze
        # just that one frame a few times to cancel out per-call noise, then blend those.
        topn = []
        for reg, fl in by_region.items():
            best = max(fl, key=lambda x: x.get("confidence", 0))
            ensembled, spread = await _ensemble_frame(best, session_id) if precision else (best, None)
            ref_frame = await _reference_scored_frame(
                best["storage_path"], best.get("view") or "scan", reg, session_id, previous,
            ) if precision else None
            frames_for_region = [ensembled] + ([ref_frame] if ref_frame else [])
            reg_metrics = {k: _avg_real(frames_for_region, k) for k in METRIC_KEYS}
            hairline = _avg_hairline(frames_for_region)
            if hairline is not None:
                reg_metrics["hairline_score"] = hairline
            representative = dict(ensembled)
            representative.update(reg_metrics)
            topn.append(representative)
            if spread is not None:
                reg_metrics["spread"] = spread
                region_spreads.append(spread)
            region_storage_path[reg] = best["storage_path"]
            # Scalp map is crown-only (see _generate_scalp_map's docstring).
            reg_metrics["scalp_map_path"] = await _generate_scalp_map(best["storage_path"], user["user_id"], session_id, reg) if reg == "crown" else None
            per_region[reg] = reg_metrics

    def avg(key: str) -> int:
        return _avg_real(topn, key)

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


async def process_scan(user: dict, session_id: str, region: str, raw_frames: list[tuple[bytes, str]], precision: bool) -> None:
    """Background counterpart of the old synchronous /scan body: process each
    raw captured frame, score it, save it, then finalize the day's analysis --
    all off the request/response cycle, since a full multi-region scan makes
    enough LLM calls that doing this inline was tripping the reverse proxy's
    origin timeout. There's no request left to return a result to, so progress
    is only observable via tracking_sessions.processing + whether an analysis
    doc exists yet; the frontend polls GET /sessions/{id} for both. Any
    failure is logged and leaves processing=False with no analysis doc rather
    than surfacing an error anywhere -- the frontend's "not analyzed yet" state
    already covers that case.
    """
    await db.tracking_sessions.update_one({"id": session_id}, {"$set": {"processing": True}})
    try:
        processed = []
        too_blurry = []
        for raw, sub in raw_frames:
            try:
                proc, _ = await asyncio.to_thread(image_utils.process_image, raw)
            except Exception:
                continue
            # Free, deterministic reject-gate for obviously-unusable frames --
            # catches them before an API call is spent finding out. A frame
            # whose blur can't even be measured (decode failure inside
            # blur_variance) is treated as usable rather than silently
            # dropped; only a REAL sub-threshold reading rejects it.
            bv = await asyncio.to_thread(image_utils.blur_variance, proc)
            if bv is not None and bv < BLUR_VARIANCE_MIN:
                too_blurry.append((proc, sub))
                continue
            processed.append((proc, sub))
        if not processed:
            # Every frame was rejected as too blurry (or none decoded at all) --
            # score what we have rather than losing the whole scan; a real,
            # if blurry, reading beats no reading.
            processed = too_blurry
        if not processed:
            logger.warning(f"process_scan: no valid frames for session {session_id}")
            return

        sem = asyncio.Semaphore(6)

        async def analyze_one(i, proc, sub):
            async with sem:
                b64 = await asyncio.to_thread(image_utils.to_base64_jpeg_for_scoring, proc)
                m = await ai_service.analyze_metrics(b64, "scan", f"{session_id}-{i}", region=sub)
            return proc, sub, m

        results = await asyncio.gather(*[analyze_one(i, p, sub) for i, (p, sub) in enumerate(processed)])

        for proc, sub, m in results:
            img_id = str(uuid.uuid4())
            base = f"{store.APP_NAME}/uploads/{user['user_id']}/{img_id}"
            r1 = await asyncio.to_thread(store.put_object, f"{base}.jpg", proc, "image/jpeg")
            thumb = await asyncio.to_thread(image_utils.make_thumbnail, proc)
            await asyncio.to_thread(store.put_object, f"{base}_thumb.jpg", thumb, "image/jpeg")
            img_doc = {
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
            await db.images.insert_one(dict(img_doc))

        await finalize_day_analysis(user, session_id, region, precision=precision)
    except Exception:
        logger.exception(f"process_scan failed for session {session_id}")
    finally:
        await db.tracking_sessions.update_one({"id": session_id}, {"$set": {"processing": False}})
