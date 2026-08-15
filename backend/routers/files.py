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
        user = await get_current_user(request, authorization or (f"Bearer {auth}" if auth else None))
    except HTTPException:
        raise HTTPException(status_code=401, detail="Not authenticated")
    record = await db.images.find_one({"$or": [{"storage_path": path}, {"thumb_path": path}]}, {"_id": 0})
    if not record:
        # Derived images (e.g. change-map heatmaps, scalp maps) intentionally
        # aren't rows in db.images -- they're not captured photos, so they
        # shouldn't show up in galleries/delete/export. Allow a user to fetch
        # only their own, scoped by their own user_id baked into the path at
        # creation time.
        own_derived_prefixes = (
            f"{store.APP_NAME}/changemaps/{user['user_id']}/",
            f"{store.APP_NAME}/scalpmaps/{user['user_id']}/",
        )
        if not path.startswith(own_derived_prefixes):
            raise HTTPException(status_code=404, detail="File not found")
    data, ctype = await asyncio.to_thread(store.get_object, path)
    return StreamingResponse(io.BytesIO(data), media_type=ctype)
