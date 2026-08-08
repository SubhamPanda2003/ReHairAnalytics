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

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
MAX_SIZE = 10 * 1024 * 1024
ALLOWED_EXT = {"jpg", "jpeg", "png"}
VIEWS = {"front", "left", "right", "top", "back"}


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
    return user


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
    resp = http_requests.get(EMERGENT_SESSION_URL, headers={"X-Session-ID": body.session_id}, timeout=30)
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session id")
    data = resp.json()
    email = data["email"]
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user = {
            "user_id": user_id,
            "email": email,
            "name": data.get("name", ""),
            "picture": data.get("picture", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(dict(user))
    else:
        await db.users.update_one({"email": email}, {"$set": {"name": data.get("name", user.get("name", "")), "picture": data.get("picture", user.get("picture", ""))}})

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


@api_router.get("/sessions")
async def list_sessions(request: Request, authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    sessions = await db.tracking_sessions.find({"user_id": user["user_id"]}, {"_id": 0}).sort("week_number", 1).to_list(1000)
    for s in sessions:
        s["images"] = await db.images.find({"tracking_session_id": s["id"]}, {"_id": 0}).to_list(20)
        s["analysis"] = await db.analysis.find_one({"tracking_session_id": s["id"]}, {"_id": 0})
    return sessions


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
    frames.sort(key=lambda f: f.get("confidence", 0), reverse=True)
    topn = frames[: min(4, len(frames))]

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
async def auto_scan(request: Request, files: List[UploadFile] = File(...), region: str = Form("full"), authorization: Optional[str] = Header(None)):
    user = await get_current_user(request, authorization)
    if region not in ("full", "crown", "hairline"):
        region = "full"
    session = await get_or_create_today_session(user["user_id"])
    session_id = session["id"]

    processed = []
    for f in files[:12]:
        raw = await f.read()
        if not raw or len(raw) > MAX_SIZE:
            continue
        try:
            proc, _ = image_utils.process_image(raw)
            processed.append(proc)
        except Exception:
            continue
    if not processed:
        raise HTTPException(status_code=400, detail="No valid frames captured")

    async def analyze_one(i, proc):
        b64 = image_utils.to_base64_jpeg(proc)
        m = await ai_service.analyze_metrics(b64, "scan", f"{session_id}-{i}", region=region)
        return proc, m

    results = await asyncio.gather(*[analyze_one(i, p) for i, p in enumerate(processed)])

    for proc, m in results:
        img_id = str(uuid.uuid4())
        base = f"{store.APP_NAME}/uploads/{user['user_id']}/{img_id}"
        r1 = store.put_object(f"{base}.jpg", proc, "image/jpeg")
        thumb = image_utils.make_thumbnail(proc)
        store.put_object(f"{base}_thumb.jpg", thumb, "image/jpeg")
        doc = {
            "id": img_id,
            "tracking_session_id": session_id,
            "user_id": user["user_id"],
            "view": "scan",
            "region": region,
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

    processed, ctype = image_utils.process_image(raw)
    thumb = image_utils.make_thumbnail(processed)
    b64 = image_utils.to_base64_jpeg(processed)

    quality = await ai_service.analyze_quality(b64, view, session_id)
    if quality["quality"] < 60:
        return {"rejected": True, "quality_score": quality["quality"], "issues": quality["issues"], "retry": True}

    img_id = str(uuid.uuid4())
    base_path = f"{store.APP_NAME}/uploads/{user['user_id']}/{img_id}"
    img_path = f"{base_path}.jpg"
    thumb_path = f"{base_path}_thumb.jpg"
    r1 = store.put_object(img_path, processed, ctype)
    store.put_object(thumb_path, thumb, "image/jpeg")

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
    data, _ = store.get_object(primary["storage_path"])
    b64 = image_utils.to_base64_jpeg(data)
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
    for s in sessions:
        s["images"] = await db.images.find({"tracking_session_id": s["id"]}, {"_id": 0}).to_list(20)
        s["analysis"] = await db.analysis.find_one({"tracking_session_id": s["id"]}, {"_id": 0})
    return sessions


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
    data, ctype = store.get_object(path)
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
