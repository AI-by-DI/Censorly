# ai/inference/pipeline_redact.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse
import json
import pathlib
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

import cv2
import numpy as np

def log(*a): print(*a, flush=True)

# ---------- IO / parsing ----------

def load_events(jsonl_path: str, labels: Optional[List[str]], min_score: float) -> List[dict]:
    evs = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s: continue
            e = json.loads(s)
            if labels and e.get("label") not in labels: 
                continue
            if float(e.get("score", 0.0)) < min_score:
                continue
            e["ts_ms"] = int(e["ts_ms"])
            evs.append(e)
    evs.sort(key=lambda x: (x["label"], x["ts_ms"]))
    log(f"[i] JSONL yüklendi: {jsonl_path} (filtre sonrası {len(evs)} satır)")
    return evs

# ---------- geometry ----------

def yolo_bbox_to_xyxy(bbox: List[float], W: int, H: int) -> Tuple[int, int, int, int]:
    cx, cy, w, h = bbox
    x1 = int(round((cx - w/2) * W)); y1 = int(round((cy - h/2) * H))
    x2 = int(round((cx + w/2) * W)); y2 = int(round((cy + h/2) * H))
    x1 = max(0, min(W-1, x1)); y1 = max(0, min(H-1, y1))
    x2 = max(0, min(W-1, x2)); y2 = max(0, min(H-1, y2))
    if x2 < x1: x1, x2 = x2, x1
    if y2 < y1: y1, y2 = y2, y1
    return x1, y1, x2, y2

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def interp_bbox(t: int, t0: int, b0: List[float], t1: int, b1: List[float]) -> List[float]:
    """Lineer interpolasyon; t0==t1 ise b0 döner."""
    if t1 == t0: 
        return b0
    alpha = max(0.0, min(1.0, (t - t0) / float(t1 - t0)))
    return [lerp(b0[i], b1[i], alpha) for i in range(4)]

# ---------- segmentation (temporal smoothing) ----------

def build_segments(events: List[dict], hold_gap_ms: int, grace_ms: int) -> List[dict]:
    """
    Aynı label için ardışık ts farkı <= hold_gap_ms ise TEK segment olarak birleştir.
    Segment yapısı: {label, start_ms, end_ms, keys:[(ts_ms, bbox, score)]}
    end_ms segment kapanışına grace_ms eklenerek tutulur.
    """
    by_label: Dict[str, List[dict]] = defaultdict(list)
    for e in events:
        by_label[e["label"]].append(e)

    segments: List[dict] = []
    for lab, lst in by_label.items():
        lst.sort(key=lambda x: x["ts_ms"])
        cur_keys: List[Tuple[int, List[float], float]] = []
        seg_start = None
        last_ts = None
        for e in lst:
            ts = e["ts_ms"]
            if seg_start is None:
                seg_start = ts
                cur_keys = [(ts, e["bbox"], float(e.get("score", 0.0)))]
                last_ts = ts
                continue
            gap = ts - last_ts
            if gap <= hold_gap_ms:
                # aynı segment devam
                cur_keys.append((ts, e["bbox"], float(e.get("score", 0.0))))
                last_ts = ts
            else:
                # önceki segmenti kapat
                seg_end = last_ts + grace_ms
                segments.append({
                    "label": lab,
                    "start_ms": seg_start,
                    "end_ms": seg_end,
                    "keys": cur_keys[:],  # kopya
                })
                # yeni segment başlat
                seg_start = ts
                cur_keys = [(ts, e["bbox"], float(e.get("score", 0.0)))]
                last_ts = ts
        if seg_start is not None:
            seg_end = (last_ts or seg_start) + grace_ms
            segments.append({
                "label": lab,
                "start_ms": seg_start,
                "end_ms": seg_end,
                "keys": cur_keys[:],
            })

    # okunurluk için sıralayalım
    segments.sort(key=lambda s: (s["start_ms"], s["label"]))
    log(f"[i] segment sayısı: {len(segments)}")
    return segments

def bbox_at_time(seg: dict, t_ms: int) -> Optional[Tuple[List[float], float]]:
    """
    t_ms segment aralığındaysa iki keyframe arasında interpolasyonla bbox döndür.
    Score'u da iki keyframe arasında lineer karıştırıyoruz (görsel etki için).
    """
    keys = seg["keys"]
    if not keys:
        return None
    # t seg aralığında mı?
    if t_ms < seg["start_ms"] or t_ms > seg["end_ms"]:
        return None
    # tek keyframe
    if len(keys) == 1:
        return keys[0][1], keys[0][2]
    # uygun iki keyframe'i bul
    # (liste küçük; lineer arama yeterli, istenirse binary search yapılır)
    for i in range(len(keys)-1):
        t0, b0, s0 = keys[i]
        t1, b1, s1 = keys[i+1]
        if t_ms <= t1:
            b = interp_bbox(t_ms, t0, b0, t1, b1)
            s = lerp(s0, s1, 0.0 if t1==t0 else (t_ms - t0)/max(1,(t1 - t0)))
            return b, s
    # son keyframe'den sonra ise son bbox'u kullan (grace için)
    return keys[-1][1], keys[-1][2]

# ---------- drawing ----------

def draw_red_box_fill(img: np.ndarray, x1:int, y1:int, x2:int, y2:int, label:str, score:float) -> None:
    if x2 <= x1 or y2 <= y1: return
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), thickness=-1)  # solid red
    txt = f"{label} {score:.2f}"
    (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    band_h = th + 10
    yb1 = max(0, y1 - band_h)
    cv2.rectangle(img, (x1, yb1), (x1 + tw + 10, y1), (0, 0, 200), thickness=-1)
    cv2.putText(img, txt, (x1 + 5, max(0, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2, cv2.LINE_AA)

# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(
        description="JSONL tespitlerini segmentleyip (temporal hold) videoya DOLU kırmızı kutu olarak uygular."
    )
    ap.add_argument("--video", required=True, help="Giriş video (lokal .mp4)")
    ap.add_argument("--jsonl", required=True, help="Inference JSONL")
    ap.add_argument("--out",   required=True, help="Çıkış video (mp4)")
    ap.add_argument("--labels", default="", help="Virgülle etiket filtre (örn: violence,alcohol). Boş=hepsi")
    ap.add_argument("--min_score", type=float, default=0.5, help="Skor eşiği")
    ap.add_argument("--hold_gap_ms", type=int, default=600, help="Aynı segmentte saymak için ardışık tespitler arası azami fark (ms).")
    ap.add_argument("--grace_ms", type=int, default=200, help="Segment sonunda ek görünürlük süresi (ms).")
    args = ap.parse_args()

    labels = [s.strip() for s in args.labels.split(",") if s.strip()] if args.labels else None
    log("[cfg] video=", args.video)
    log("[cfg] jsonl=", args.jsonl)
    log("[cfg] out  =", args.out)
    log("[cfg] labels=", labels or "<all>", "min_score=", args.min_score, 
        "hold_gap_ms=", args.hold_gap_ms, "grace_ms=", args.grace_ms)

    # video meta
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    log(f"[i] video info: {W}x{H} @ {fps:.3f} fps")

    # olaylar -> segmentler
    evs = load_events(args.jsonl, labels, args.min_score)
    segments = build_segments(evs, hold_gap_ms=args.hold_gap_ms, grace_ms=args.grace_ms)

    # writer
    def open_writer(path: str):
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        vw = cv2.VideoWriter(path, fourcc, fps, (W, H))
        if vw.isOpened(): return vw
        fourcc = cv2.VideoWriter_fourcc(*"avc1")
        return cv2.VideoWriter(path, fourcc, fps, (W, H))
    out = open_writer(args.out)
    if not out or not out.isOpened():
        raise RuntimeError(f"Cannot open writer: {args.out}")

    # render
    frame_idx = 0
    applied = 0
    secs = defaultdict(lambda: defaultdict(int))
    instants = []  # (ts_ms,label) gerçek olaylar
    for e in evs:
        instants.append((e["ts_ms"], e["label"]))

    while True:
        ok, frame = cap.read()
        if not ok: break
        ts_ms = int(round(frame_idx * 1000.0 / fps))
        sec = ts_ms // 1000

        # her segment için aktifse çiz (liste küçükse sade döngü yeter; çok büyükse sweep-line yapılabilir)
        for seg in segments:
            if seg["start_ms"] <= ts_ms <= seg["end_ms"]:
                bb = bbox_at_time(seg, ts_ms)
                if bb is None:
                    continue
                bbox_norm, score = bb
                x1, y1, x2, y2 = yolo_bbox_to_xyxy(bbox_norm, W, H)
                draw_red_box_fill(frame, x1, y1, x2, y2, seg["label"], float(score))
                applied += 1
                secs[sec][seg["label"]] += 1

        out.write(frame)
        frame_idx += 1
        if frame_idx % 100 == 0:
            log(f"[prog] frame={frame_idx} applied_boxes={applied}")

    cap.release()
    out.release()

    # raporlar
    out_dir = pathlib.Path(args.out)
    # saniye özeti
    seconds_csv = out_dir.with_suffix(".seconds.csv")
    with open(seconds_csv, "w", encoding="utf-8") as f:
        f.write("second,label,count\n")
        for s in sorted(secs.keys()):
            for lab, cnt in sorted(secs[s].items()):
                f.write(f"{s},{lab},{cnt}\n")
    # segment özeti
    segments_csv = out_dir.with_suffix(".segments.csv")
    with open(segments_csv, "w", encoding="utf-8") as f:
        f.write("label,start_ms,end_ms,duration_ms,n_keyframes\n")
        for seg in segments:
            f.write(f"{seg['label']},{seg['start_ms']},{seg['end_ms']},{seg['end_ms']-seg['start_ms']},{len(seg['keys'])}\n")
    # anlık liste (ham olaylar)
    instants_csv = out_dir.with_suffix(".instants.csv")
    with open(instants_csv, "w", encoding="utf-8") as f:
        f.write("ts_ms,label\n")
        for ts, lab in sorted(instants):
            f.write(f"{ts},{lab}\n")

    log(f"[✓] Bitti → {args.out}")
    log(f"[→] Çizilen kutu adedi (frame-bazlı): {applied}")
    log(f"[→] Saniye özeti   : {seconds_csv}")
    log(f"[→] Segment özeti  : {segments_csv}")
    log(f"[→] Anlık liste    : {instants_csv}")

if __name__ == "__main__":
    main()
