"""Auth dependencies shared by every router."""
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, Request

from . import config
from models.database import db


async def get_current_user(request: Request, authorization: Optional[str] = Header(None)) -> dict:
    """Resolve the caller from a session cookie or `Authorization: Bearer` header.

    Also callable directly (not just via Depends) so routes that need a custom
    fallback for the token source, e.g. file downloads via query string, can
    build the `authorization` value themselves and pass it in.
    """
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

    # The fixed super admin always holds the super_admin role, even if the DB drifted.
    if config.SUPER_ADMIN_EMAIL and (user.get("email", "").lower() == config.SUPER_ADMIN_EMAIL) and user.get("role") != "super_admin":
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"role": "super_admin"}})
        user["role"] = "super_admin"
    if "role" not in user:
        user["role"] = "user"
    return user


def require_roles(user: dict, *roles: str) -> None:
    if user.get("role") not in roles:
        raise HTTPException(status_code=403, detail="Forbidden")


CurrentUser = Annotated[dict, Depends(get_current_user)]
