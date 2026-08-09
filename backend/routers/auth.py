"""Session exchange, current-user lookup, and logout."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests as http_requests
from fastapi import APIRouter, Header, HTTPException, Request, Response

from utils import config
from models.database import db
from utils.deps import CurrentUser
from models.schemas import SessionExchange

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/session")
async def auth_session(body: SessionExchange, response: Response):
    resp = await asyncio.to_thread(
        lambda: http_requests.get(config.EMERGENT_SESSION_URL, headers={"X-Session-ID": body.session_id}, timeout=30)
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session id")
    data = resp.json()
    email = (data["email"] or "").strip().lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        role = "super_admin" if (config.SUPER_ADMIN_EMAIL and email.lower() == config.SUPER_ADMIN_EMAIL) else "user"
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
        if config.SUPER_ADMIN_EMAIL and email.lower() == config.SUPER_ADMIN_EMAIL:
            upd["role"] = "super_admin"
        elif "role" not in user:
            upd["role"] = "user"
        await db.users.update_one({"email": email}, {"$set": upd})
        user.update(upd)

    session_token = data.get("session_token") or uuid.uuid4().hex
    expires = datetime.now(timezone.utc) + timedelta(days=config.SESSION_TTL_DAYS)
    await db.user_sessions.insert_one({
        "user_id": user["user_id"],
        "session_token": session_token,
        "expires_at": expires.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    response.set_cookie(
        key="session_token", value=session_token, httponly=True, secure=True,
        samesite="none", path="/", max_age=config.SESSION_TTL_DAYS * 24 * 60 * 60,
    )
    user.pop("_id", None)
    return {"user": user}


@router.get("/me")
async def auth_me(user: CurrentUser):
    profile = await db.profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    user["profile"] = profile
    user["is_dermatologist"] = bool(await db.dermatologist_profiles.find_one({"user_id": user["user_id"]}, {"_id": 1}))
    return user


@router.post("/logout")
async def auth_logout(request: Request, response: Response, authorization: Optional[str] = Header(None)):
    token = request.cookies.get("session_token") or (authorization.split(" ", 1)[1] if authorization and authorization.startswith("Bearer ") else None)
    if token:
        await db.user_sessions.delete_many({"session_token": token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}
