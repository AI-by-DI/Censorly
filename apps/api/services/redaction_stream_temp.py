# apps/api/services/redaction_stream_temp.py  (yalnız fark: out temp dosya)
import tempfile, os, subprocess
from starlette.responses import StreamingResponse
# ... yukarıdaki ortak yardımcılar aynı ...

def stream_blur_via_temp(db, user_id: str, video_id: str, profile_id: Optional[str]) -> StreamingResponse:
    # profil/job/video/thr/blur hazırlığı yukarıdakiyle aynı...
    # ...
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name

    cmd = [
        "python","-m","ai.inference.pipeline_redact",
        "--video", video_arg,
        "--jsonl", jsonl_arg,
        "--out", tmp_path,
        "--min_score_map", min_map_str,
        "--hold_gap_ms", str(blur["hold_gap_ms"]),
        "--grace_ms",    str(blur["grace_ms"]),
        "--mode", "blur",
        "--blur_k", str(blur["blur_k"]),
        "--box_thick", str(blur["box_thick"]),
        "--keep_audio"
    ]
    subprocess.run(cmd, check=True)

    def _iter_file():
        try:
            with open(tmp_path, "rb") as f:
                while True:
                    b = f.read(64 * 1024)
                    if not b: break
                    yield b
        finally:
            try: os.remove(tmp_path)
            except OSError: pass

    return StreamingResponse(_iter_file(), media_type="video/mp4", headers={"Cache-Control":"no-store"})