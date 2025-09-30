#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cut per-class TN clips & snapshots from a CSV of timestamps.

CSV beklenen kolonlar:
- timestamp_ms (zorunlu, milisaniye)
- label        (zorunlu)
- video        (opsiyonel; yoksa --video ile verilmeli)

Örnek:
python cut_tn_clips.py \
  --csv tn_frames__spider-clown-blood-violence__thr0.55.csv \
  --video /path/to/source.mp4 \
  --outdir ./tn_exports \
  --clip_dur 3.0 \
  --min_gap 1.0 \
  --snapshots
"""

import argparse
import subprocess
from pathlib import Path
import pandas as pd


def safe_name(x: str) -> str:
    """File-system friendly name."""
    s = str(x)
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in s)


def has_col(df: pd.DataFrame, name: str) -> bool:
    return name in df.columns and df[name].notna().any()


def cut_clip(video: Path, t_center_s: float, out_path: Path,
             duration: float, reencode: str = "libx264", crf: int = 23) -> None:
    """Cut a short clip centered at t_center_s (seconds)."""
    start = max(t_center_s - duration / 2.0, 0.0)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-i", str(video),
        "-t", f"{duration:.3f}",
        "-c:v", reencode,
        "-crf", str(crf),
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def save_snapshot(video: Path, t_center_s: float, out_path: Path) -> None:
    """Save a single PNG frame around t_center_s."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{t_center_s:.3f}",
        "-i", str(video),
        "-frames:v", "1",
        str(out_path),
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def main():
    ap = argparse.ArgumentParser(description="Cut per-class TN clips & snapshots from a CSV of timestamps.")
    ap.add_argument("--csv", required=True, help="TN CSV path (expects timestamp_ms, label[, video])")
    ap.add_argument("--video", default=None, help="Fallback video path if CSV has no 'video' column")
    ap.add_argument("--outdir", default="tn_exports", help="Output directory root")
    ap.add_argument("--clip_dur", type=float, default=3.0, help="Clip duration in seconds (default 3.0)")
    ap.add_argument("--min_gap", type=float, default=1.0, help="De-dup gap per label (seconds)")
    ap.add_argument("--snapshots", action="store_true", help="Also save PNG snapshots")
    ap.add_argument("--reencode", default="libx264", help="ffmpeg video codec (default libx264)")
    ap.add_argument("--crf", type=int, default=23, help="ffmpeg CRF (lower = higher quality)")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)

    # Basic checks
    if not has_col(df, "timestamp_ms"):
        raise SystemExit("CSV must contain 'timestamp_ms' column (milliseconds).")
    if not has_col(df, "label"):
        raise SystemExit("CSV must contain 'label' column.")

    # Determine video source column
    if has_col(df, "video"):
        df["video_src"] = df["video"].astype(str)
    else:
        if not args.video:
            raise SystemExit("CSV has no 'video' column. Please provide --video path.")
        df["video_src"] = str(args.video)

    out_root = Path(args.outdir)
    out_root.mkdir(parents=True, exist_ok=True)

    # Normalize timestamp to seconds
    df = df.copy()
    df["t_s"] = pd.to_numeric(df["timestamp_ms"], errors="coerce").fillna(0) / 1000.0

    # Process per class/label
    for label, g in df.groupby("label"):
        label_safe = safe_name(label if pd.notna(label) else "unknown")
        label_dir = out_root / label_safe
        label_dir.mkdir(parents=True, exist_ok=True)

        # De-dup near timestamps for the same (video,label)
        round_to = max(float(args.min_gap), 0.1)
        g = g.copy()
        g["t_round"] = (g["t_s"] / round_to).round() * round_to

        seen = set()
        g = g.sort_values(["video_src", "t_s"])
        for _, row in g.iterrows():
            video = Path(row["video_src"])
            t_s = float(row["t_s"])
            key = (str(video), float(row["t_round"]))
            if key in seen:
                continue
            seen.add(key)

            base = f"{video.stem}__{label_safe}__{t_s:.3f}s"
            clip_path = label_dir / f"{base}.mp4"
            cut_clip(video, t_s, clip_path, duration=args.clip_dur,
                     reencode=args.reencode, crf=args.crf)

            if args.snapshots:
                png_path = label_dir / f"{base}.png"
                save_snapshot(video, t_s, png_path)

    print(f"Done. Outputs under: {out_root.resolve()}")


if __name__ == "__main__":
    main()
