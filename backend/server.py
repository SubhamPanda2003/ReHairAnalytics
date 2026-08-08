import os
import uuid
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import FastAPI, APIRouter, UploadFile, File, Form, HTTPException, Header, Request, Response, Query
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
import requests as http_requests
import io

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import storage as store
import image_utils
import ai_service

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="ReHairAnalytics API")
api_router = APIRouter(prefix="/api")


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/api/health")
async def api_health():
    return {"status": "healthy"}


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
MAX_SIZE = 10 * 1024 * 1024
ALLOWED_EXT = {"jpg", "jpeg", "png"}
VIEWS = {"front", "left", "right", "top", "back"}
SUPER_ADMIN_EMAIL = (os.environ.get("SUPER_ADMIN_EMAIL") or "").strip().lower()


# ---------------- Auth helpers ----------------
async def get_current_user(request: Request, authorization: Optional[str] = None):
    token = request.cookies.get("session_token")
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    expires_at = session["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    # Ensure the fixed super admin always has the super_admin role.
    if SUPER_ADMIN_EMAIL and (user.get("email", "").lower() == SUPER_ADMIN_EMAIL) and user.get("role") != "super_admin":
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"role": "super_admin"}})
        user["role"] = "super_admin"
    if "role" not in user:
        user["role"] = "user"
    return user


def require_roles(user: dict, *roles):
    if user.get("role") not in roles:
        raise HTTPException(status_code=403, detail="Forbidden")


# ---------------- Models ----------------
class SessionExchange(BaseModel):
    session_id: str


class ProfileIn(BaseModel):
    age: Optional[int] = None
    gender: Optional[str] = None
    hair_type: Optional[str] = None
    goals: Optional[str] = None
    reminder_enabled: Optional[bool] = None
    reminder_day: Optional[str] = None


class SessionIn(BaseModel):
    notes: Optional[str] = ""


class DermRegisterIn(BaseModel):
    name: str
    specialty: str
    years_experience: Optional[int] = None
    bio: Optional[str] = ""
    photo: Optional[str] = ""
    meeting_link: str
    price: Optional[str] = ""


class AppointmentIn(BaseModel):
    dermatologist_id: str
    requested_time: str
    note: Optional[str] = ""


class RoleIn(BaseModel):
    role: str


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def get_or_create_today_session(user_id: str, notes: str = ""):
    d = today_str()
    existing = await db.tracking_sessions.find_one({"user_id": user_id, "day": d}, {"_id": 0})
    if existing:
        return existing
    count = await db.tracking_sessions.count_documents({"user_id": user_id})
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "week_number": count,
        "day": d,
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


# ---------------- Auth routes ----------------
@api_router.post("/auth/session")
async def auth_session(body: SessionExchange, response: Response):
    resp = await asyncio.to_thread(
        lambda: http_requests.get(EMERGENT_SESSION_URL, headers={"X-Session-ID": body.session_id}, timeout=30)
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session id")
    data = resp.json()
    email = (data["email"] or "").strip().lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        role = "super_admin" if (SUPER_ADMIN_EMAIL and email.lower() == SUPER_ADMIN_EMAIL) else "user"
        user = {
            "user_id": user_id,
            "email": email,
            "name": data.get("name", ""),
            "picture": data.get("picture", ""),
            "role": role,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(dict(user))
    else:
        upd = {"name": data.get("name", user.get("name", "")), "picture": data.get("picture", user.get("picture", ""))}
        if SUPER_ADMIN_EMAIL and email.lower() == SUPER_ADMIN_EMAIL:
            upd["role"] = "super_admin"
        elif "role" not in user:
            upd["role"] = "user"
        await db.users.update_one({"email": email}, {"$set": upd})
        user.update(upd)

    session_token = data.get("session_token") or uuid.uuid4().hex
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({
        "user_id": user["user_id"],
        "session_token": session_token,
        "expires_at": expires.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    response.set_cookie(
        key="session_token", value=session_token, httponly=True, secure=True,
        samesite="none", path="/", max_age=7 * 24 * 60 * 60,
    )
    user.pop("_id", None)
    return {"user": user}


@api_router.get("/auth/me")
async def auth_me(request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    profile = await db.profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    user["profile"] = profile
    user["is_dermatologist"] = bool(await db.dermatologist_profiles.find_one({"user_id": user["user_id"]}, {"_id": 1}))
    return user


@api_router.post("/auth/logout")
async def auth_logout(request: Request, response: Response, authorization: Optional[str] = Header(None)):
    token = request.cookies.get("session_token") or (authorization.split(" ", 1)[1] if authorization and authorization.startswith("Bearer ") else None)
    if token:
        await db.user_sessions.delete_many({"session_token": token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


# ---------------- Profile ----------------
@api_router.get("/profile")
async def get_profile(request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    profile = await db.profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return profile or {}


@api_router.post("/profile")
async def upsert_profile(body: ProfileIn, request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    doc = body.model_dump(exclude_unset=True)
    doc["user_id"] = user["user_id"]
    existing = await db.profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if existing:
        await db.profiles.update_one({"user_id": user["user_id"]}, {"$set": doc})
    else:
        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.profiles.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


# ---------------- Tracking sessions ----------------
@api_router.post("/sessions")
async def create_session(body: SessionIn, request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    doc = await get_or_create_today_session(user["user_id"], body.notes or "")
    return doc


async def _attach_children(sessions):
    ids = [s["id"] for s in sessions]
    if not ids:
        return sessions
    imgs = await db.images.find({"tracking_session_id": {"$in": ids}}, {"_id": 0}).to_list(20000)
    ans = await db.analysis.find({"tracking_session_id": {"$in": ids}}, {"_id": 0}).to_list(2000)
    img_map = {}
    for im in imgs:
        img_map.setdefault(im["tracking_session_id"], []).append(im)
    ana_map = {a["tracking_session_id"]: a for a in ans}
    for s in sessions:
        s["images"] = img_map.get(s["id"], [])
        s["analysis"] = ana_map.get(s["id"])
    return sessions


@api_router.get("/sessions")
async def list_sessions(request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    sessions = await db.tracking_sessions.find({"user_id": user["user_id"]}, {"_id": 0}).sort("week_number", 1).to_list(1000)
    return await _attach_children(sessions)


@api_router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    s = await db.tracking_sessions.find_one({"id": session_id, "user_id": user["user_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    imgs = await db.images.find({"tracking_session_id": session_id}, {"_id": 0}).to_list(200)
    imgs.sort(key=lambda i: (i.get("confidence", 0), i.get("quality_score", 0)), reverse=True)
    s["images"] = imgs
    s["analysis"] = await db.analysis.find_one({"tracking_session_id": session_id}, {"_id": 0})
    s["current_best_image"] = imgs[0].get("storage_path") if imgs else None
    # comparisons
    all_sessions = await db.tracking_sessions.find({"user_id": user["user_id"]}, {"_id": 0}).sort("week_number", 1).to_list(1000)
    prev = None
    baseline = None
    prev_best = None
    baseline_best = None
    if all_sessions:
        baseline_id = all_sessions[0]["id"]
        baseline = await db.analysis.find_one({"tracking_session_id": baseline_id}, {"_id": 0})
        baseline_best = await best_image_path(baseline_id)
        idx = next((i for i, x in enumerate(all_sessions) if x["id"] == session_id), 0)
        if idx > 0:
            prev = await db.analysis.find_one({"tracking_session_id": all_sessions[idx - 1]["id"]}, {"_id": 0})
            prev_best = await best_image_path(all_sessions[idx - 1]["id"])
    s["previous_analysis"] = prev
    s["previous_best_image"] = prev_best
    is_baseline = bool(baseline and baseline.get("tracking_session_id") == session_id)
    s["baseline_analysis"] = None if is_baseline else baseline
    s["baseline_best_image"] = None if is_baseline else baseline_best
    return s


async def finalize_day_analysis(user: dict, session_id: str, region: str):
    frames = await db.images.find({"tracking_session_id": session_id, "confidence": {"$exists": True}}, {"_id": 0}).to_list(300)
    if not frames:
        raise HTTPException(status_code=400, detail="No analyzable frames")
    BLUR_QUALITY_MIN = 40
    usable = [f for f in frames if f.get("quality_score", 0) >= BLUR_QUALITY_MIN] or frames

    METRIC_KEYS = ["hairline_score", "density_score", "coverage_score", "overall_score",
                   "confidence", "quality_score", "visible_scalp_pct", "hair_coverage_pct"]

    # Group usable frames by their captured (sub-)region.
    by_region = {}
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

    def avg(k):
        return int(round(sum(f.get(k, 0) for f in topn) / len(topn)))

    metrics = {
        "hairline_score": avg("hairline_score"),
        "density_score": avg("density_score"),
        "coverage_score": avg("coverage_score"),
        "overall_score": avg("overall_score"),
        "confidence": avg("confidence"),
        "visible_scalp_pct": avg("visible_scalp_pct"),
        "hair_coverage_pct": avg("hair_coverage_pct"),
    }

    all_sessions = await db.tracking_sessions.find({"user_id": user["user_id"]}, {"_id": 0}).sort("week_number", 1).to_list(1000)
    baseline_id = all_sessions[0]["id"] if all_sessions else session_id
    baseline = await db.analysis.find_one({"tracking_session_id": baseline_id}, {"_id": 0})
    idx = next((i for i, x in enumerate(all_sessions) if x["id"] == session_id), 0)
    previous = None
    if idx > 0:
        previous = await db.analysis.find_one({"tracking_session_id": all_sessions[idx - 1]["id"]}, {"_id": 0})

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

    def deltas(cur, ref):
        if not ref:
            return None
        return {
            "density": round(cur["density_score"] - ref["density_score"], 1),
            "coverage": round(cur["coverage_score"] - ref["coverage_score"], 1),
            "hairline": round(cur["hairline_score"] - ref["hairline_score"], 1),
            "overall": round(cur["overall_score"] - ref["overall_score"], 1),
        }

    return {
        "session_id": session_id,
        "analysis": doc,
        "vs_previous": deltas(metrics, previous),
        "vs_baseline": deltas(metrics, baseline) if (baseline and baseline.get("tracking_session_id") != session_id) else None,
    }


@api_router.post("/scan")
async def auto_scan(request: Request, files: List[UploadFile] = File(...), region: str = Form("full"), frame_regions: List[str] = Form([]), authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    if region not in ("full", "crown", "hairline"):
        region = "full"
    session = await get_or_create_today_session(user["user_id"])
    session_id = session["id"]

    regions_in = frame_regions or []
    processed = []  # list of (proc, sub_region)
    for i, f in enumerate(files[:36]):
        raw = await f.read()
        if not raw or len(raw) > MAX_SIZE:
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

    return await finalize_day_analysis(user, session_id, region)


@api_router.post("/sessions/{session_id}/upload")
async def upload_image(session_id: str, request: Request, file: UploadFile = File(...), view: str = Form(...), authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    s = await db.tracking_sessions.find_one({"id": session_id, "user_id": user["user_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if view not in VIEWS:
        raise HTTPException(status_code=400, detail="Invalid view")
    ext = (file.filename or "").split(".")[-1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="Only jpg, jpeg, png allowed")
    raw = await file.read()
    if len(raw) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="Max size 10MB")

    processed, ctype = await asyncio.to_thread(image_utils.process_image, raw)
    thumb = await asyncio.to_thread(image_utils.make_thumbnail, processed)
    b64 = await asyncio.to_thread(image_utils.to_base64_jpeg, processed)

    quality = await ai_service.analyze_quality(b64, view, session_id)
    if quality["quality"] < 60:
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


@api_router.post("/sessions/{session_id}/analyze")
async def analyze_session(session_id: str, request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
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

    # comparisons
    all_sessions = await db.tracking_sessions.find({"user_id": user["user_id"]}, {"_id": 0}).sort("week_number", 1).to_list(1000)
    baseline_id = all_sessions[0]["id"] if all_sessions else session_id
    baseline = await db.analysis.find_one({"tracking_session_id": baseline_id}, {"_id": 0})
    idx = next((i for i, x in enumerate(all_sessions) if x["id"] == session_id), 0)
    previous = None
    if idx > 0:
        previous = await db.analysis.find_one({"tracking_session_id": all_sessions[idx - 1]["id"]}, {"_id": 0})

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

    def deltas(cur, ref):
        if not ref:
            return None
        return {
            "density": round(cur["density_score"] - ref["density_score"], 1),
            "coverage": round(cur["coverage_score"] - ref["coverage_score"], 1),
            "hairline": round(cur["hairline_score"] - ref["hairline_score"], 1),
            "overall": round(cur["overall_score"] - ref["overall_score"], 1),
        }

    return {
        "analysis": doc,
        "vs_previous": deltas(metrics, previous),
        "vs_baseline": deltas(metrics, baseline) if (baseline and baseline.get("tracking_session_id") != session_id) else None,
    }


# ---------------- Timeline & Progress ----------------
@api_router.get("/timeline")
async def timeline(request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    sessions = await db.tracking_sessions.find({"user_id": user["user_id"]}, {"_id": 0}).sort("week_number", 1).to_list(1000)
    return await _attach_children(sessions)


@api_router.get("/progress")
async def progress(request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
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


# ---------------- Files ----------------
@api_router.get("/files/{path:path}")
async def download_file(path: str, request: Request, authorization: Optional[str] = Header(None), auth: Optional[str] = Query(None)):
    try:
        await get_current_user(request, authorization or (f"Bearer {auth}" if auth else None))
    except HTTPException:
        raise HTTPException(status_code=401, detail="Not authenticated")
    record = await db.images.find_one({"$or": [{"storage_path": path}, {"thumb_path": path}]}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    data, ctype = await asyncio.to_thread(store.get_object, path)
    return StreamingResponse(io.BytesIO(data), media_type=ctype)


# ---------------- Export & Delete ----------------
@api_router.get("/export")
async def export_data(request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    profile = await db.profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    sessions = await db.tracking_sessions.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    images = await db.images.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    analysis = await db.analysis.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {"name": user.get("name"), "email": user.get("email")},
        "profile": profile,
        "tracking_sessions": sessions,
        "images": images,
        "analysis": analysis,
    }


@api_router.delete("/account")
async def delete_account(request: Request, response: Response, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    uid = user["user_id"]
    await db.images.update_many({"user_id": uid}, {"$set": {"is_deleted": True}})
    await db.images.delete_many({"user_id": uid})
    await db.analysis.delete_many({"user_id": uid})
    await db.tracking_sessions.delete_many({"user_id": uid})
    await db.profiles.delete_many({"user_id": uid})
    await db.user_sessions.delete_many({"user_id": uid})
    await db.users.delete_many({"user_id": uid})
    response.delete_cookie("session_token", path="/")
    return {"deleted": True}


# ---------------- Dermatologists ----------------
def _derm_public(d: dict, include_link: bool = False) -> dict:
    out = {
        "user_id": d.get("user_id"),
        "name": d.get("name"),
        "specialty": d.get("specialty"),
        "years_experience": d.get("years_experience"),
        "bio": d.get("bio"),
        "photo": d.get("photo"),
        "price": d.get("price"),
        "status": d.get("status"),
    }
    if include_link:
        out["meeting_link"] = d.get("meeting_link")
    return out


@api_router.post("/derm/register")
async def derm_register(body: DermRegisterIn, request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    existing = await db.dermatologist_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if existing:
        status = existing.get("status", "pending")
        # Re-review if a previously approved dermatologist changes key public details.
        if status == "approved" and (
            existing.get("name") != body.name
            or existing.get("specialty") != body.specialty
            or existing.get("meeting_link") != body.meeting_link
        ):
            status = "pending"
    else:
        status = "pending"
    doc = {
        "user_id": user["user_id"],
        "email": user.get("email"),
        "name": body.name,
        "specialty": body.specialty,
        "years_experience": body.years_experience,
        "bio": body.bio or "",
        "photo": body.photo or user.get("picture", ""),
        "meeting_link": body.meeting_link,
        "price": body.price or "",
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        await db.dermatologist_profiles.update_one({"user_id": user["user_id"]}, {"$set": doc})
    else:
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.dermatologist_profiles.insert_one(dict(doc))
    # promote role to dermatologist unless already admin/super_admin
    if user.get("role") not in ("admin", "super_admin"):
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"role": "dermatologist"}})
    doc.pop("_id", None)
    return doc


@api_router.get("/derm/me")
async def derm_me(request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    d = await db.dermatologist_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return d or {}


@api_router.get("/dermatologists")
async def list_dermatologists(request: Request, authorization: Optional[str] = Header(None)):
    await get_current_user(request, authorization)
    docs = await db.dermatologist_profiles.find({"status": "approved"}, {"_id": 0}).to_list(500)
    return [_derm_public(d) for d in docs]


# ---------------- Admin ----------------
@api_router.get("/admin/dermatologists")
async def admin_list_derms(request: Request, status: Optional[str] = Query(None), authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    require_roles(user, "admin", "super_admin")
    q = {"status": status} if status else {}
    docs = await db.dermatologist_profiles.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return docs


@api_router.post("/admin/dermatologists/{derm_user_id}/approve")
async def admin_approve_derm(derm_user_id: str, request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    require_roles(user, "admin", "super_admin")
    r = await db.dermatologist_profiles.update_one({"user_id": derm_user_id}, {"$set": {"status": "approved"}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Dermatologist not found")
    return {"status": "approved"}


@api_router.post("/admin/dermatologists/{derm_user_id}/reject")
async def admin_reject_derm(derm_user_id: str, request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    require_roles(user, "admin", "super_admin")
    r = await db.dermatologist_profiles.update_one({"user_id": derm_user_id}, {"$set": {"status": "rejected"}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Dermatologist not found")
    return {"status": "rejected"}


@api_router.get("/admin/users")
async def admin_list_users(request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    require_roles(user, "super_admin")
    users = await db.users.find({}, {"_id": 0, "user_id": 1, "email": 1, "name": 1, "picture": 1, "role": 1}).to_list(2000)
    for u in users:
        u.setdefault("role", "user")
    return users


@api_router.post("/admin/users/{target_user_id}/role")
async def admin_set_role(target_user_id: str, body: RoleIn, request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    require_roles(user, "super_admin")
    if body.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Role must be 'user' or 'admin'")
    target = await db.users.find_one({"user_id": target_user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("email", "").lower() == SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=400, detail="Cannot change the super admin")
    await db.users.update_one({"user_id": target_user_id}, {"$set": {"role": body.role}})
    return {"user_id": target_user_id, "role": body.role}


# ---------------- Appointments ----------------
@api_router.post("/appointments")
async def create_appointment(body: AppointmentIn, request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    derm = await db.dermatologist_profiles.find_one({"user_id": body.dermatologist_id, "status": "approved"}, {"_id": 0})
    if not derm:
        raise HTTPException(status_code=404, detail="Dermatologist not available")
    doc = {
        "id": str(uuid.uuid4()),
        "patient_id": user["user_id"],
        "patient_name": user.get("name", ""),
        "patient_email": user.get("email", ""),
        "dermatologist_id": body.dermatologist_id,
        "derm_name": derm.get("name", ""),
        "requested_time": body.requested_time,
        "note": body.note or "",
        "status": "requested",
        "meeting_link": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.appointments.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@api_router.get("/appointments")
async def list_appointments(request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    as_patient = await db.appointments.find({"patient_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    as_derm = await db.appointments.find({"dermatologist_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"as_patient": as_patient, "as_dermatologist": as_derm}


@api_router.post("/appointments/{appt_id}/confirm")
async def confirm_appointment(appt_id: str, request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    appt = await db.appointments.find_one({"id": appt_id}, {"_id": 0})
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt["dermatologist_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    derm = await db.dermatologist_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    link = derm.get("meeting_link") if derm else None
    await db.appointments.update_one({"id": appt_id}, {"$set": {"status": "confirmed", "meeting_link": link}})
    return {"status": "confirmed", "meeting_link": link}


@api_router.post("/appointments/{appt_id}/decline")
async def decline_appointment(appt_id: str, request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    appt = await db.appointments.find_one({"id": appt_id}, {"_id": 0})
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt["dermatologist_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    await db.appointments.update_one({"id": appt_id}, {"$set": {"status": "declined"}})
    return {"status": "declined"}


@api_router.post("/appointments/{appt_id}/cancel")
async def cancel_appointment(appt_id: str, request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    appt = await db.appointments.find_one({"id": appt_id}, {"_id": 0})
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt["patient_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    await db.appointments.update_one({"id": appt_id}, {"$set": {"status": "cancelled"}})
    return {"status": "cancelled"}


@api_router.get("/")
async def root():
    return {"message": "ReHairAnalytics API", "status": "ok"}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    try:
        store.init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
