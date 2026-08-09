"""Authenticated retrieval of stored images/thumbnails."""
import asyncio
import io
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from services import storage as store
from models.database import db
from utils.deps import get_current_user

router = APIRouter(tags=["files"])


@router.get("/files/{path:path}")
async def download_file(
    path: str,
    request: Request,
    authorization: Optional[str] = Header(None),
    auth: Optional[str] = Query(None),
):
    try:
        await get_current_user(request, authorization or (f"Bearer {auth}" if auth else None))
    except HTTPException:
        raise HTTPException(status_code=401, detail="Not authenticated")
    record = await db.images.find_one({"$or": [{"storage_path": path}, {"thumb_path": path}]}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    data, ctype = await asyncio.to_thread(store.get_object, path)
    return StreamingResponse(io.BytesIO(data), media_type=ctype)
