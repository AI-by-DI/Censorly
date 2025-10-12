# apps/api/routers/videos.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from apps.api.schemas.redaction import RenderRequest, RenderResult
from apps.api.core.db import get_db
from apps.api.routers.auth import get_current_user
from apps.api.services.redaction_service import render_or_get
from apps.api.services.redaction_stream import stream_blur_live 

router = APIRouter(prefix="/videos", tags=["videos"])

@router.post("/{video_id}/render", response_model=RenderResult)
def render_video(video_id: str, body: RenderRequest, db: Session = Depends(get_db), user = Depends(get_current_user)):
    try:
        res = render_or_get(db, user_id=str(user.id), video_id=video_id, profile_id=body.profile_id)
        return RenderResult(ok=True, **res)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{video_id}/stream", response_model=RenderResult)
def stream_video(
    video_id: str,
    profile_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    try:
        res = render_or_get(db, user_id=str(user.id), video_id=video_id, profile_id=profile_id)
        return RenderResult(ok=True, **res)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
router = APIRouter(prefix="/redactions", tags=["redactions"])

@router.get("/stream/{video_id}")
def stream_redacted(
    video_id: str,
    profile_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    try:
        return stream_blur_live(db, user_id=str(user.id), video_id=video_id, profile_id=profile_id)
        # stdout desteklenmiyorsa:
        # return stream_blur_via_temp(db, user_id=str(user.id), video_id=video_id, profile_id=profile_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))