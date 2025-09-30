# ai/inference/ffmpeg_utils.py
from __future__ import annotations
import cv2, math
from typing import Iterator, Tuple
import numpy as np

def iter_frames_with_timestamps(video_path: str, stride_ms: int) -> Iterator[Tuple[int, "np.ndarray"]]:
    """
    stride_ms aralığıyla kareleri verir: (ts_ms, frame[BGR])
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur_ms = int(1000 * frame_count / fps) if frame_count > 0 else None

    next_ts = 0
    while True:
        # hedef frame index hesapla
        target_frame_idx = int(round(next_ts * fps / 1000.0))
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_idx)
        ok, frame = cap.read()
        if not ok:
            break
        yield next_ts, frame
        next_ts += stride_ms

        if dur_ms is not None and next_ts > dur_ms:
            break

    cap.release()
