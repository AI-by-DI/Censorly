# apps/api/routers/redactions.py
from __future__ import annotations
import os, tempfile, subprocess, logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Security
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from apps.api.core.db import get_db
from data.schema import VideoAsset
from apps.api.services.redaction_stream import (
    _build_audio_filter_from_intervals, _calc_skip_intervals, _ffprobe_duration, _get_profile, _invert_to_keep, profile_to_dict, _latest_done_job, _jsonl_path_abs,
    _build_jsonl_from_db, _build_min_score_map, _labels_from_mode_map, _ensure_canon_labels_jsonl
)

# 🔗 MinIO utils
from apps.api.utils.minio_utils import (
    resolve_source_to_local, upload_redacted_and_presign,
)

# ---- JWT ----
import jwt
from pydantic import BaseModel

JWT_SECRET = os.getenv("JWT_SECRET", "devsecret")
JWT_ALG = os.getenv("JWT_ALG", "HS256")

# Redacted presigned URL ömrü (saat)
REDACT_TTL_HOURS = int(os.getenv("REDACT_TTL_HOURS", "3"))

# Redactor komutu
REDACTOR_CMD = os.getenv("REDACTOR_CMD", "python -m ai.inference.pipeline_redact")

log = logging.getLogger("api.redactions")

class _User(BaseModel):
  id: str

# --- helper: file has audio? ---
def _has_audio(path: str) -> bool:
  try:
    p = subprocess.run(
      ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "default=noprint_wrappers=1", path],
      capture_output=True, text=True
    )
    return "codec_type=audio" in (p.stdout or "")
  except Exception:
    # ffprobe yoksa kaba kontrol
    p = subprocess.run(["ffmpeg", "-v", "quiet", "-i", path, "-f", "null", "-"], capture_output=True, text=True)
    return "Audio:" in (p.stderr or "")  
  
def _media_duration(path: str) -> float:
    """Saniye cinsinden duration; bilinmiyorsa 0 döner."""
    try:
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True
        )
        return float(p.stdout.strip() or 0)
    except Exception:
        return 0.0  

def _decode_user_from_token(token: Optional[str]) -> Optional[_User]:
  if not token:
    return None
  try:
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG], options={"require": ["sub"]})
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
    raise HTTPException(status_code=401, detail="Authorization required (Bearer or ?access_token=).")
  return u

router = APIRouter(prefix="/redactions", tags=["redactions"])



@router.get("/download/{video_id}", name="download_now",
            summary="Sansürlü MP4'ü üretir veya hazırsa presigned URL döner.")
def download_now(
  video_id: UUID,
  profile_id: str = Query("active", description="Kullanıcı tercih profili ID"),
  presigned: bool = Query(
    True,
    description="True: MinIO presigned URL JSON döner; False: temp dosyayı response ile döner"
  ),
  db: Session = Depends(get_db),
  user: _User = Depends(resolve_user),
  background: BackgroundTasks = None,
):
  src_tmp: Optional[str] = None

  try:
    # 0) Video
    vid = db.get(VideoAsset, str(video_id))
    if not vid:
      raise HTTPException(status_code=404, detail=f"Video not found (video_id={video_id})")

    # Kaynağı local path'e çöz (MinIO ise indir → temp)
    try:
      video_arg, src_tmp = resolve_source_to_local(vid.storage_key)
    except Exception as e:
      log.exception("resolve_source_to_local failed")
      raise HTTPException(status_code=502, detail=f"source_resolve_failed: {e}")

    # 1) Profil
    prof = _get_profile(db, current_user_id=str(user.id), profile_id=profile_id)
    if not prof:
      raise HTTPException(status_code=404, detail=f"Preference profile not found (user_id={user.id}, profile_id={profile_id})")

    pd = profile_to_dict(prof)
    ex = pd.get("extras") or {}
    mode_map = pd.get("mode_map") or {}
    if not mode_map:
      raise HTTPException(status_code=400, detail="No filters active; stream original from MinIO.")

    # 2) Analiz job & JSONL
    job = _latest_done_job(db, str(video_id))
    if not job:
      raise HTTPException(status_code=404, detail=f"No completed analysis for this video (video_id={video_id})")

    jsonl_arg = _jsonl_path_abs(str(job.id))
    if not os.path.exists(jsonl_arg):
      try:
        jsonl_arg = _build_jsonl_from_db(db, str(job.id))
      except Exception as e:
        log.exception("_build_jsonl_from_db failed")
        raise HTTPException(status_code=500, detail=f"jsonl_build_failed: {e}")
    jsonl_arg = _ensure_canon_labels_jsonl(jsonl_arg)  

    # 2.a) HAZIR OBJE VARSA ÖNCE ONU PRESIGN ET VE DÖN
    rb = getattr(job, "redacted_bucket", None)
    ro = getattr(job, "redacted_object", None)
    if presigned and rb and ro:
      try:
        info = upload_redacted_and_presign(
          local_path=None,
          src_storage_key=vid.storage_key,
          video_id=str(video_id),
          ttl_hours=max(1, REDACT_TTL_HOURS),
          existing_object=(rb, ro),
        )
        if src_tmp and os.path.exists(src_tmp):
          try: os.unlink(src_tmp)
          except: pass
        return JSONResponse({
          "video_id": str(video_id),
          "mode_map": mode_map,
          "min_score_map": _build_min_score_map(ex),
          "redacted": info,
        })
      except Exception as e:
        log.warning("presign existing redacted failed, will re-generate. err=%s", e)

    # 3) mode_map → label kovaları
    try:
      labels_blur, labels_red, labels_skip = _labels_from_mode_map(db, str(job.id), mode_map)
    except Exception as e:
      log.exception("_labels_from_mode_map failed")
      raise HTTPException(status_code=400, detail=f"labels_build_failed: {e}")

    if not (labels_blur or labels_red or labels_skip):
      raise HTTPException(status_code=400, detail="No labels selected for filtering.")

    has_skip = bool(labels_skip)  # ← ses graft kararında kullanacağız

    # 4) min_score_map
    try:
      min_map = _build_min_score_map(ex)
      min_map_str = ",".join([f"{k}:{float(v):.2f}" for k, v in min_map.items()])
    except Exception as e:
      log.exception("_build_min_score_map failed")
      raise HTTPException(status_code=400, detail=f"min_score_map_invalid: {e}")

    # 5) REDACT → local geçici mp4
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
      subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
      log.error("pipeline_redact failed. stdout=%s\nstderr=%s", e.stdout[-1000:], e.stderr[-1000:])
      raise HTTPException(status_code=500, detail=f"redact_failed: {e.stderr[:500]}")

    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
      raise HTTPException(status_code=500, detail="redact_empty_output")

    # 6) H.264/AAC + faststart remux (audio fix)
    fixed_path = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    try:
        if labels_skip:
            # Skip varsa: sesi orijinalden keep aralıklarına göre oluştur
            orig_ms = int(_ffprobe_duration(video_arg) * 1000)
            skips = _calc_skip_intervals(
                jsonl_arg,
                labels_skip=labels_skip,
                min_score_map=_build_min_score_map(ex),
                hold_gap_ms=int((ex.get("blur_params") or {}).get("hold_gap_ms", 600)),
                grace_ms=int((ex.get("blur_params") or {}).get("grace_ms", 200)),
                min_skip_ms=2000,
            )
            keep = _invert_to_keep(orig_ms, skips)
            fc, _ = _build_audio_filter_from_intervals(keep)

            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-fflags", "+genpts",
                    "-i", out_path,   # 0: redacted (video)
                    "-i", video_arg,  # 1: original (audio source)
                    "-filter_complex", fc,
                    "-map", "0:v:0", "-map", "[aout]",
                    # >>> video'yu H.264'e yeniden kodla (tarayıcı dostu)
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k",
                    "-shortest",
                    "-movflags", "+faststart",
                    fixed_path
                ],
                check=True, capture_output=True, text=True
            )
        else:
            # Skip yoksa:
            if _has_audio(out_path):
                # Redacted dosyada ses var → yine de uyumluluk için H.264'e remux/encode et
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-fflags", "+genpts",
                        "-i", out_path,
                        "-map", "0:v:0", "-map", "0:a:0?",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                        "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "128k",
                        "-movflags", "+faststart",
                        fixed_path
                    ],
                    check=True, capture_output=True, text=True
                )
            else:
                # Redacted sessiz → orijinalden sesi graft et
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-fflags", "+genpts",
                        "-i", out_path,
                        "-i", video_arg,
                        "-map", "0:v:0", "-map", "1:a:0?",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                        "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "128k",
                        "-shortest",
                        "-movflags", "+faststart",
                        fixed_path
                    ],
                    check=True, capture_output=True, text=True
                )
    except subprocess.CalledProcessError as e:
        log.error("ffmpeg remux failed. stdout=%s\nstderr=%s", e.stdout[-1000:], e.stderr[-1000:])
        try: os.unlink(out_path)
        except: pass
        raise HTTPException(status_code=500, detail=f"remux_failed: {e.stderr[:500]}")
    finally:
        try: os.unlink(out_path)
        except: pass


    if not os.path.exists(fixed_path):
      raise HTTPException(status_code=500, detail="remux_no_output")

    # 7) MinIO'ya yükle + presign
    if presigned:
      try:
        info = upload_redacted_and_presign(
          local_path=fixed_path,
          src_storage_key=vid.storage_key,
          video_id=str(video_id),
          ttl_hours=max(1, REDACT_TTL_HOURS),
        )
      except Exception as e:
        log.exception("upload_redacted_and_presign failed")
        try: os.unlink(fixed_path)
        except: pass
        if src_tmp and os.path.exists(src_tmp):
          try: os.unlink(src_tmp)
          except: pass
        raise HTTPException(status_code=502, detail=f"presign_failed: {e}")

      # cleanup
      try: os.unlink(fixed_path)
      except: pass
      if src_tmp and os.path.exists(src_tmp):
        try: os.unlink(src_tmp)
        except: pass

      return JSONResponse({
        "video_id": str(video_id),
        "mode_map": mode_map,
        "min_score_map": min_map,
        "redacted": info,
      })

    # 8) presigned=False → dosyayı direkt dön
    if src_tmp and os.path.exists(src_tmp):
      try: os.unlink(src_tmp)
      except: pass

    if background is not None:
      background.add_task(lambda p: os.path.exists(p) and os.unlink(p), fixed_path)

    return FileResponse(fixed_path, media_type="video/mp4", filename=f"{video_id}_redacted.mp4")

  except HTTPException:
    raise
  except Exception as e:
    log.exception("download_now crashed")
    raise HTTPException(status_code=500, detail=f"internal_error: {e}")
