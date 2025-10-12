# apps/api/routers/redactions.py
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

# DB session
from apps.api.core.db import get_db

# Auth dependency (projene göre routers.auth ya da services.auth_service)
try:
    from apps.api.routers.auth import get_current_user
except ImportError:  # fallback
    from apps.api.services.auth_service import get_current_user  # type: ignore

# Stream servisimiz (mevcut akış)
from apps.api.services.redaction_stream import stream_blur_live

# Download-now için gerekli yardımcılar
try:
    from apps.api.services.redaction_stream import (  # type: ignore
        _get_profile,
        profile_to_dict,
        _blocked,
        _thr_map,
        _blur,
        _latest_done_job,
        _jsonl_path_abs,
        _build_jsonl_from_db,
    )
    _HAVE_JSONL_HELPERS = True
except Exception:
    _HAVE_JSONL_HELPERS = False

from data.schema import VideoAsset  # video.storage_key, vs.

# -----------------------------------------------------------------------------
# Router
# -----------------------------------------------------------------------------
router = APIRouter(prefix="/redactions", tags=["redactions"])

# -----------------------------------------------------------------------------
# STREAM (mevcut endpoint — dosya kaydı yok)
# -----------------------------------------------------------------------------
@router.get(
    "/stream/{video_id}",
    summary="Anlık blur uygulanmış videoyu stream eder (dosya kaydetmez)",
    operation_id="redactions_stream",
)
def stream_redacted(
    video_id: UUID,
    profile_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
):
    try:
        return stream_blur_live(
            db,
            user_id=str(user.id),
            video_id=str(video_id),
            profile_id=profile_id,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")

# -----------------------------------------------------------------------------
# DOWNLOAD-NOW — anlık üret, geçici dosyayı indir (kalıcı kaydetmez)
# -----------------------------------------------------------------------------
@router.get(
    "/download-now/{video_id}",
    summary="Sansürlü MP4'ü anlık üretip indir (dosya kaydetmez)",
)
def download_now(
    video_id: UUID,
    profile_id: str = Query(...),
    background: BackgroundTasks = None,  # temp dosyayı response sonrası silmek için
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
):
    try:
        # 0) Video
        vid = db.get(VideoAsset, str(video_id))
        if not vid:
            raise FileNotFoundError(f"Video not found (video_id={video_id})")
        video_arg = vid.storage_key
        if not video_arg or not os.path.exists(video_arg):
            raise FileNotFoundError(f"Video file not found: {video_arg}")

        # 1) Profil & ayarlar
        if not _HAVE_JSONL_HELPERS:
            raise HTTPException(
                status_code=500,
                detail="Server missing helpers: please update redaction_stream helpers.",
            )

        prof = _get_profile(db, current_user_id=str(user.id), profile_id=profile_id)
        if not prof:
            raise ValueError(f"Preference profile not found (user_id={user.id}, profile_id={profile_id})")

        pd   = profile_to_dict(prof)
        cats = _blocked(pd)
        thr  = _thr_map(pd)
        blur = _blur(pd)

        # Sansür gerekmiyorsa orijinal dosyayı indir
        if not cats:
            fname = f"{video_id}_original.mp4"
            return FileResponse(video_arg, media_type="video/mp4", filename=fname)

        # 2) Job + JSONL
        job = _latest_done_job(db, str(video_id))
        if not job:
            raise FileNotFoundError(f"No completed analysis for this video (video_id={video_id})")

        if _HAVE_JSONL_HELPERS:
            jsonl_arg = _jsonl_path_abs(str(job.id))
            if not os.path.exists(jsonl_arg):
                jsonl_arg = _build_jsonl_from_db(db, str(job.id))
        else:
            APP_ROOT = Path(os.getenv("APP_ROOT", "/app")).resolve()
            JOBS_PREFIX = os.getenv("JOBS_JSONL_PREFIX", "uploads/jobs").strip("/").strip()
            p = (APP_ROOT / JOBS_PREFIX / str(job.id) / "jsonl").resolve()
            jsonl_arg = str(p)
            if not os.path.exists(jsonl_arg):
                raise FileNotFoundError(f"Analysis jsonl not found: {jsonl_arg}")

        # 3) Redact'ı temp'e yaz
        min_map_str = ",".join([f"{k}:{float(v):.2f}" for k, v in thr.items()])
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.close()
        out_path = tmp.name

        cmd = [
            "python", "-m", "ai.inference.pipeline_redact",
            "--video", video_arg,
            "--jsonl", jsonl_arg,
            "--out", out_path,
            "--min_score_map", min_map_str,
            "--hold_gap_ms", str(blur["hold_gap_ms"]),
            "--grace_ms",    str(blur["grace_ms"]),
            "--mode", "blur",
            "--blur_k", str(blur["blur_k"]),
            "--box_thick", str(blur["box_thick"]),
            "--keep_audio",                 # ← ALT ÇİZGİ (doğru argüman)
        ]

        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0 or not os.path.exists(out_path):
            try: os.unlink(out_path)
            except Exception: pass
            err = (proc.stderr or b"").decode(errors="ignore")
            raise HTTPException(status_code=500, detail=f"Redact failed: {err[:1000]}")

        # 4) QuickTime/tarayıcı hızlı başlatma için remux (+faststart) — yeniden encode YOK
        fixed_path = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
        remux = subprocess.run(
            ["ffmpeg", "-y", "-i", out_path, "-c", "copy", "-movflags", "+faststart", fixed_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        try: os.unlink(out_path)
        except Exception: pass

        if remux.returncode != 0 or not os.path.exists(fixed_path):
            try: os.unlink(fixed_path)
            except Exception: pass
            err = (remux.stderr or b"").decode(errors="ignore")
            raise HTTPException(status_code=500, detail=f"Remux failed: {err[:1000]}")

        # 5) İndirilebilir response (response biter bitmez temp sil)
        if background is not None:
            background.add_task(lambda p: os.path.exists(p) and os.unlink(p), fixed_path)

        fname = f"{video_id}_redacted.mp4"
        return FileResponse(fixed_path, media_type="video/mp4", filename=fname)

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")