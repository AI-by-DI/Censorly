# apps/api/routers/redactions.py
from __future__ import annotations
import os, tempfile, subprocess
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Security
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from apps.api.core.db import get_db
from data.schema import VideoAsset
from apps.api.services.redaction_stream import (
    _get_profile, profile_to_dict, _latest_done_job, _jsonl_path_abs,
    _build_jsonl_from_db, _build_min_score_map, _labels_from_mode_map
)


# 🔗 MinIO utils (tek yerden yönetelim: public endpoint/region/presign tutarlı olsun)
from apps.api.utils.minio_utils import (
    resolve_source_to_local, upload_redacted_and_presign,
)

# ---- JWT ----
import jwt
from pydantic import BaseModel


JWT_SECRET = os.getenv("JWT_SECRET", "devsecret")
JWT_ALG = os.getenv("JWT_ALG", "HS256")

# Redacted geçicilik (presigned URL süresi). MinIO presigned üst limiti 7 gün.
REDACT_TTL_HOURS = int(os.getenv("REDACT_TTL_HOURS", "3"))

# 🔧 Redactor komutu ENV’den (API imajında bu modül/binary olmalı)
REDACTOR_CMD = os.getenv("REDACTOR_CMD", "python -m ai.inference.pipeline_redact")

class _User(BaseModel):
    id: str

def _decode_user_from_token(token: Optional[str]) -> Optional[_User]:
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, JWT_SECRET, algorithms=[JWT_ALG], options={"require": ["sub"]}
        )
        sub = str(payload.get("sub") or "")
        return _User(id=sub) if sub else None
    except Exception:
        return None

_http_bearer = HTTPBearer(auto_error=False)

def resolve_user(
    access_token: Optional[str] = Query(default=None),
    creds: HTTPAuthorizationCredentials | None = Security(_http_bearer),
) -> _User:
    tok = (creds.credentials if creds else None) or access_token
    u = _decode_user_from_token(tok)
    if not u:
        raise HTTPException(
            status_code=401, detail="Authorization required (Bearer or ?access_token=)."
        )
    return u

router = APIRouter(prefix="/redactions", tags=["redactions"])

# ---------------------------------------------------------------------
# Sansürlü MP4'ü üret: MinIO'ya yükle (geçici) ve presigned URL dön.
# ---------------------------------------------------------------------
@router.get("/download/{video_id}", name="download_now",
            summary="Sansürlü MP4'ü üretir. Varsayılan: Presigned URL döner.")
def download_now(
    video_id: UUID,
    background: BackgroundTasks,  # <-- default'suzlar önce
    profile_id: str = Query(..., description="Kullanıcı tercih profili ID"),
    presigned: bool = Query(
        True,
        description="True: MinIO presigned URL JSON döner; False: temp dosyayı response ile döner"
    ),
    db: Session = Depends(get_db),
    user: _User = Depends(resolve_user),
):


    src_tmp: Optional[str] = None
    try:
        # 0) Kaynak video
        vid = db.get(VideoAsset, str(video_id))
        if not vid:
            raise FileNotFoundError(f"Video not found (video_id={video_id})")

        # Kaynağı local path'e çöz (MinIO ise indir → temp)
        video_arg, src_tmp = resolve_source_to_local(vid.storage_key)

        # 1) Profil ve ayarlar
        prof = _get_profile(db, current_user_id=str(user.id), profile_id=profile_id)
        if not prof:
            raise ValueError(
                f"Preference profile not found (user_id={user.id}, profile_id={profile_id})"
            )

        pd = profile_to_dict(prof)
        ex = pd.get("extras") or {}
        mode_map = pd.get("mode_map") or {}

        if not mode_map:
            # Kullanıcı hiç filtre istememiş → orijinali stream et
            raise HTTPException(
                status_code=400,
                detail="No filters active; stream original from MinIO."
            )

        # 2) Analiz job ve JSONL
        job = _latest_done_job(db, str(video_id))
        if not job:
            raise FileNotFoundError(
                f"No completed analysis for this video (video_id={video_id})"
            )

        jsonl_arg = _jsonl_path_abs(str(job.id))
        if not os.path.exists(jsonl_arg):
            jsonl_arg = _build_jsonl_from_db(db, str(job.id))

        # 3) mode_map → label kovaları
        labels_blur, labels_red, labels_skip = _labels_from_mode_map(db, str(job.id), mode_map)
        if not (labels_blur or labels_red or labels_skip):
            raise HTTPException(status_code=400, detail="No labels selected for filtering.")

        # 4) min_score_map
        min_map = _build_min_score_map(ex)
        min_map_str = ",".join([f"{k}:{float(v):.2f}" for k, v in min_map.items()])

        # 5) Redact → local geçici mp4
        # 5) redact → geçici mp4 (local)
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False); tmp.close()
        out_path = tmp.name

        cmd = [
            "python", "-m", "ai.inference.pipeline_redact",
            "--video", video_arg,
            "--jsonl", jsonl_arg,
            "--out", out_path,
            "--labels_blur", ",".join(labels_blur),
            "--labels_red",  ",".join(labels_red),
            "--labels_skip", ",".join(labels_skip),
            "--min_skip_ms", "2000",
            "--min_score_map", min_map_str,
            "--hold_gap_ms", str((ex.get("blur_params") or {}).get("hold_gap_ms", 600)),
            "--grace_ms",    str((ex.get("blur_params") or {}).get("grace_ms", 200)),
            "--blur_k",      str((ex.get("blur_params") or {}).get("blur_k", 80)),
            "--box_thick",   str((ex.get("blur_params") or {}).get("box_thick", 4)),
            "--keep_audio",
            "--min_keyframes_map", "default:1",
        ]

        try:
            proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Redact failed: {e.stderr[:1000]}"
            )

        if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
            raise HTTPException(status_code=500, detail="Redact produced empty file.")

        # 6) H.264/AAC'e encode + faststart
        fixed_path = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
        try:
            remux = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", out_path,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                    "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart",
                    fixed_path
                ],
                check=True, capture_output=True, text=True
            )
        finally:
            try: os.unlink(out_path)
            except: pass


        if remux.returncode != 0 or not os.path.exists(fixed_path):
            err = (remux.stderr or b"").decode(errors="ignore")
            out = (remux.stdout or b"").decode(errors="ignore")
            try:
                os.unlink(fixed_path)
            except Exception:
                pass
            raise HTTPException(
                status_code=500,
                detail=f"Remux failed: {err[:1000]}\n--- stdout ---\n{out[:1000]}"
            )

        # 7) Varsayılan: MinIO'ya yükle → Presigned URL dön
        if presigned:
            info = upload_redacted_and_presign(
                local_path=fixed_path,
                src_storage_key=vid.storage_key,
                video_id=str(video_id),
                ttl_hours=max(1, REDACT_TTL_HOURS),
            )
            # local temp temizliği
            try: os.unlink(fixed_path)
            except Exception: pass
            if src_tmp and os.path.exists(src_tmp):
                try: os.unlink(src_tmp)
                except Exception: pass

            return JSONResponse({
                "video_id": str(video_id),
                "mode_map": mode_map,
                "min_score_map": min_map,
                "redacted": info,  # {bucket, object, url, expires_in_seconds}
            })

        # Eski davranış: dosyayı response ile döndür (ve cleanup)
        if src_tmp and os.path.exists(src_tmp):
            try: os.unlink(src_tmp)
            except Exception: pass

        if background is not None:
            background.add_task(lambda p: os.path.exists(p) and os.unlink(p), fixed_path)

        return FileResponse(fixed_path, media_type="video/mp4", filename=f"{video_id}_redacted.mp4")

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        # Genel hata: stack gizli tut, ama mesaj ver
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
