# apps/api/routers/redactions.py
from __future__ import annotations

import os
import tempfile
import subprocess
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Security
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from apps.api.core.db import get_db
from data.schema import VideoAsset
from apps.api.services.redaction_stream import (
    _get_profile,
    profile_to_dict,
    _latest_done_job,
    _jsonl_path_abs,
    _build_jsonl_from_db,
    _build_min_score_map,
    _labels_from_mode_map,   # <-- yeni: mode_map'ten label kovaları
)

# ---- JWT (Bearer veya ?access_token=) ----
import jwt
from pydantic import BaseModel

JWT_SECRET = os.getenv("JWT_SECRET", "devsecret")
JWT_ALG = os.getenv("JWT_ALG", "HS256")


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
# TEK ENDPOINT: Sansürlü MP4'ü anlık üret ve indir
# ---------------------------------------------------------------------
@router.get("/download/{video_id}", name="download_now", summary="Sansürlü MP4'ü anlık üretip indir.")
def download_now(
    video_id: UUID,
    profile_id: str = Query(..., description="Kullanıcı tercih profili ID"),
    background: BackgroundTasks = None,
    db: Session = Depends(get_db),
    user: _User = Depends(resolve_user),
):
    try:
        # 0) kaynak video
        vid = db.get(VideoAsset, str(video_id))
        if not vid:
            raise FileNotFoundError(f"Video not found (video_id={video_id})")
        video_arg = vid.storage_key
        if not video_arg or not os.path.exists(video_arg):
            raise FileNotFoundError(f"Video file not found: {video_arg}")

        # 1) profil & ayarlar
        prof = _get_profile(db, current_user_id=str(user.id), profile_id=profile_id)
        if not prof:
            raise ValueError(
                f"Preference profile not found (user_id={user.id}, profile_id={profile_id})"
            )

        pd = profile_to_dict(prof)
        ex = pd.get("extras") or {}
        mode_map = pd.get("mode_map") or {}

        # Kullanıcı hiçbir kategori için sansür istememiş → orijinal dön
        if not mode_map:
            return FileResponse(
                video_arg, media_type="video/mp4", filename=f"{video_id}_original.mp4"
            )

        # 2) ilgili analysis job ve jsonl
        job = _latest_done_job(db, str(video_id))
        if not job:
            raise FileNotFoundError(
                f"No completed analysis for this video (video_id={video_id})"
            )

        jsonl_arg = _jsonl_path_abs(str(job.id))
        if not os.path.exists(jsonl_arg):
            jsonl_arg = _build_jsonl_from_db(db, str(job.id))

        # 3) mode_map → label kovaları (blur/red/skip)
        labels_blur, labels_red, labels_skip = _labels_from_mode_map(db, str(job.id), mode_map)

        # Kova listeleri tamamen boşsa filtre yok → orijinal
        if not (labels_blur or labels_red or labels_skip):
            return FileResponse(
                video_arg, media_type="video/mp4", filename=f"{video_id}_original.mp4"
            )

        # 4) min_score_map (hard-coded + dinamik + kullanıcı override)
        min_map = _build_min_score_map(ex)
        min_map_str = ",".join([f"{k}:{float(v):.2f}" for k, v in min_map.items()])

        # 5) redact → geçici mp4
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.close()
        out_path = tmp.name

        cmd = [
            "python",
            "-m",
            "ai.inference.pipeline_redact",
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
            "--keep_audio",  # skip varsa pipeline içinde devre dışı bırakılıyor
            "--min_keyframes_map", "default:1",
        ]

        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0 or not os.path.exists(out_path):
            try:
                os.unlink(out_path)
            except Exception:
                pass
            err = (proc.stderr or b"").decode(errors="ignore")
            out = (proc.stdout or b"").decode(errors="ignore")
            raise HTTPException(
                status_code=500, detail=f"Redact failed: {err[:1000]}\n--- stdout ---\n{out[:1000]}"
            )

        # 6) +faststart remux (yeniden encode yok)
        fixed_path = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
        remux = subprocess.run(
            ["ffmpeg", "-y", "-i", out_path, "-c", "copy", "-movflags", "+faststart", fixed_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            os.unlink(out_path)
        except Exception:
            pass

        if remux.returncode != 0 or not os.path.exists(fixed_path):
            try:
                os.unlink(fixed_path)
            except Exception:
                pass
            err = (remux.stderr or b"").decode(errors="ignore")
            out = (remux.stdout or b"").decode(errors="ignore")
            raise HTTPException(
                status_code=500, detail=f"Remux failed: {err[:1000]}\n--- stdout ---\n{out[:1000]}"
            )

        if background is not None:
            background.add_task(lambda p: os.path.exists(p) and os.unlink(p), fixed_path)

        return FileResponse(
            fixed_path, media_type="video/mp4", filename=f"{video_id}_redacted.mp4"
        )

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")
