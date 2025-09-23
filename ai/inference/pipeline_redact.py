# ai/inference/pipeline_redact.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, json, pathlib
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

import cv2, numpy as np


def log(*a):
    print(*a, flush=True)


# ----------------- arg parsing helpers -----------------

def parse_min_score_map(arg: str, fallback: float) -> Dict[str, float]:
    """
    "violence:0.3,blood:0.75,default:0.5" -> {"violence":0.3, "blood":0.75, "default":0.5}
    """
    if not arg:
        return {"default": fallback}
    out: Dict[str, float] = {}
    for part in arg.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = float(v.strip())
        else:
            out["default"] = float(part)
    if "default" not in out:
        out["default"] = fallback
    return out


# ----------------- IO / parsing -----------------

def load_events(jsonl_path: str, labels: Optional[List[str]], min_score_map: Dict[str, float]) -> List[dict]:
    evs: List[dict] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            e = json.loads(s)
            lab = e.get("label")
            if labels and lab not in labels:
                continue
            ms = min_score_map.get(lab, min_score_map["default"])  # per-label threshold
            if float(e.get("score", 0.0)) < ms:
                continue
            e["ts_ms"] = int(e["ts_ms"])  # safety
            evs.append(e)
    evs.sort(key=lambda x: (x["label"], x["ts_ms"]))
    log(f"[i] JSONL yüklendi: {jsonl_path} (filtre sonrası {len(evs)} satır)")
    return evs


# ----------------- geometry & metrics -----------------

def yolo_bbox_to_xyxy(bbox: List[float], W: int, H: int) -> Tuple[int, int, int, int]:
    cx, cy, w, h = bbox
    x1 = int(round((cx - w / 2) * W))
    y1 = int(round((cy - h / 2) * H))
    x2 = int(round((cx + w / 2) * W))
    y2 = int(round((cy + h / 2) * H))
    x1 = max(0, min(W - 1, x1))
    y1 = max(0, min(H - 1, y1))
    x2 = max(0, min(W - 1, x2))
    y2 = max(0, min(H - 1, y2))
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return x1, y1, x2, y2


def bbox_iou(b1: List[float], b2: List[float]) -> float:
    # b: [cx,cy,w,h] normalized
    def to_xyxy(b):
        cx, cy, w, h = b
        return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2

    ax1, ay1, ax2, ay2 = to_xyxy(b1)
    bx1, by1, bx2, by2 = to_xyxy(b2)
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    aw, ah = (ax2 - ax1), (ay2 - ay1)
    bw, bh = (bx2 - bx1), (by2 - by1)
    union = aw * ah + bw * bh - inter + 1e-9
    return inter / union


def center_dist(b1: List[float], b2: List[float]) -> float:
    return ((b1[0] - b2[0]) ** 2 + (b1[1] - b2[1]) ** 2) ** 0.5  # normalized


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def interp_bbox(t: int, t0: int, b0: List[float], t1: int, b1: List[float]) -> List[float]:
    if t1 == t0:
        return b0
    alpha = max(0.0, min(1.0, (t - t0) / float(t1 - t0)))
    return [lerp(b0[i], b1[i], alpha) for i in range(4)]


# ----------------- multi-instance segmentation -----------------

def build_segments_multi(
    events: List[dict],
    hold_gap_ms: int,
    grace_ms: int,
    iou_thr: float = 0.1,
    max_center_dist: float = 0.25,
) -> List[dict]:
    """
    Aynı label için birden çok örneği (instance) paralel segmentler halinde izler.
    Eşleştirme: önce IoU, sonra merkez mesafesi. Zaman boşluğu hold_gap_ms ile köprülenir.
    Segment: {id, label, start_ms, end_ms, keys:[(ts,bbox,score)]}
    """
    segs: List[dict] = []
    next_id = 1

    by_label: Dict[str, Dict[int, List[dict]]] = defaultdict(lambda: defaultdict(list))
    for e in events:
        by_label[e["label"]][e["ts_ms"]].append(e)

    for lab, ts_map in by_label.items():
        active: List[dict] = []  # açık segmentler
        for ts in sorted(ts_map.keys()):
            detections = ts_map[ts]

            assigned = set()
            used_segments = set()

            # mevcut açık segmentlere ata
            for d_idx, e in enumerate(detections):
                best_j = -1
                best_score = -1.0
                for j, seg in enumerate(active):
                    if j in used_segments:
                        continue
                    last_ts, last_bbox, _ = seg["keys"][-1]
                    if ts - last_ts > hold_gap_ms:
                        continue
                    iou = bbox_iou(e["bbox"], last_bbox)
                    dist = center_dist(e["bbox"], last_bbox)
                    score = iou - 0.1 * dist
                    if iou < iou_thr and dist > max_center_dist:
                        continue
                    if score > best_score:
                        best_score = score
                        best_j = j
                if best_j >= 0:
                    seg = active[best_j]
                    seg["keys"].append((ts, e["bbox"], float(e.get("score", 0.0))))
                    seg["end_ms"] = ts + grace_ms
                    used_segments.add(best_j)
                    assigned.add(d_idx)

            # atanamayanlar için yeni segment aç
            for d_idx, e in enumerate(detections):
                if d_idx in assigned:
                    continue
                seg = {
                    "id": f"{lab}-{next_id}",
                    "label": lab,
                    "start_ms": e["ts_ms"],
                    "end_ms": e["ts_ms"] + grace_ms,
                    "keys": [(e["ts_ms"], e["bbox"], float(e.get("score", 0.0)))],
                }
                active.append(seg)
                next_id += 1

            # çok eski segmentleri kapat
            still_active = []
            for seg in active:
                last_ts = seg["keys"][-1][0]
                if ts - last_ts <= hold_gap_ms:
                    still_active.append(seg)
                else:
                    segs.append(seg)
            active = still_active

        # kalanları kapat
        for seg in active:
            segs.append(seg)

    segs.sort(key=lambda s: (s["start_ms"], s["label"], s["id"]))
    log(f"[i] segment sayısı (multi-instance): {len(segs)}")
    return segs


def bbox_at_time(seg: dict, t_ms: int) -> Optional[Tuple[List[float], float]]:
    keys = seg["keys"]
    if not keys:
        return None
    if t_ms < seg["start_ms"] or t_ms > seg["end_ms"]:
        return None
    if len(keys) == 1:
        return keys[0][1], keys[0][2]
    for i in range(len(keys) - 1):
        t0, b0, s0 = keys[i]
        t1, b1, s1 = keys[i + 1]
        if t_ms <= t1:
            b = interp_bbox(t_ms, t0, b0, t1, b1)
            alpha = 0.0 if t1 == t0 else (t_ms - t0) / max(1, (t1 - t0))
            s = lerp(s0, s1, alpha)
            return b, s
    return keys[-1][1], keys[-1][2]


# ----------------- drawing -----------------

def draw_red_box_fill(img, x1, y1, x2, y2, label, score, seg_id=None):
    if x2 <= x1 or y2 <= y1:
        return
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), thickness=-1)
    tag = f"{label} {score:.2f}" + (f" [{seg_id}]" if seg_id else "")
    (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    yb1 = max(0, y1 - th - 8)
    cv2.rectangle(img, (x1, yb1), (x1 + tw + 8, y1), (0, 0, 200), thickness=-1)
    cv2.putText(img, tag, (x1 + 4, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)


def draw_blur_box(img, x1, y1, x2, y2, ksize=35):
    if x2 <= x1 or y2 <= y1:
        return
    k = max(3, ksize | 1)  # tek sayı
    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return
    img[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (k, k), 0)


# ----------------- main -----------------

def main():
    ap = argparse.ArgumentParser(description="Multi-instance temporal redaction with per-label thresholds and red/blur modes.")
    ap.add_argument("--video", required=True)
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--labels", default="", help="örn: violence,alcohol,blood,phobic,obscene | boş=hepsi")
    ap.add_argument("--min_score", type=float, default=0.5, help="global default min score")
    ap.add_argument("--min_score_map", type=str, default="", help='örn: "violence:0.3,blood:0.75,default:0.5"')
    ap.add_argument("--hold_gap_ms", type=int, default=600)
    ap.add_argument("--grace_ms", type=int, default=200)
    ap.add_argument("--iou_thr", type=float, default=0.1, help="segment eşleştirme IoU eşiği")
    ap.add_argument("--max_center_dist", type=float, default=0.25, help="eşleştirme için max merkez uzaklığı (normalized)")
    ap.add_argument("--mode", choices=["red", "blur"], default="red", help="Kutu modu: red=solid kırmızı (default), blur=gaussian blur")
    ap.add_argument("--blur_k", type=int, default=35, help="Gaussian blur kernel size (tek sayı, büyüdükçe daha güçlü blur)")
    args = ap.parse_args()

    labs = [s.strip() for s in args.labels.split(",") if s.strip()] if args.labels else None
    msmap = parse_min_score_map(args.min_score_map, args.min_score)
    log("[cfg] labels=", labs or "<all>", "min_score_map=", msmap,
        "hold_gap_ms=", args.hold_gap_ms, "grace_ms=", args.grace_ms,
        "mode=", args.mode, "blur_k=", args.blur_k)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    log(f"[i] video info: {W}x{H} @ {fps:.3f} fps")

    events = load_events(args.jsonl, labs, msmap)
    segments = build_segments_multi(events, args.hold_gap_ms, args.grace_ms, args.iou_thr, args.max_center_dist)

    # writer
    def open_writer(path: str):
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        vw = cv2.VideoWriter(path, fourcc, fps, (W, H))
        if vw.isOpened():
            return vw
        fourcc = cv2.VideoWriter_fourcc(*"avc1")
        return cv2.VideoWriter(path, fourcc, fps, (W, H))

    out = open_writer(args.out)
    if not out or not out.isOpened():
        raise RuntimeError(f"Cannot open writer: {args.out}")

    frame_idx = 0
    applied = 0
    secs = defaultdict(lambda: defaultdict(int))

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        ts_ms = int(round(frame_idx * 1000.0 / fps))
        sec = ts_ms // 1000

        for seg in segments:
            if seg["start_ms"] <= ts_ms <= seg["end_ms"]:
                bb = bbox_at_time(seg, ts_ms)
                if bb is None:
                    continue
                bbox_norm, score = bb
                x1, y1, x2, y2 = yolo_bbox_to_xyxy(bbox_norm, W, H)
                if args.mode == "red":
                    draw_red_box_fill(frame, x1, y1, x2, y2, seg["label"], float(score), seg_id=seg["id"])
                else:
                    draw_blur_box(frame, x1, y1, x2, y2, ksize=args.blur_k)
                applied += 1
                secs[sec][seg["label"]] += 1

        out.write(frame)
        frame_idx += 1
        if frame_idx % 100 == 0:
            log(f"[prog] frame={frame_idx} applied_boxes={applied}")

    cap.release()
    out.release()

    # raporlar
    outp = pathlib.Path(args.out)
    seconds_csv = outp.with_suffix(".seconds.csv")
    with open(seconds_csv, "w", encoding="utf-8") as f:
        f.write("second,label,count\n")
        for s in sorted(secs.keys()):
            for lab, cnt in sorted(secs[s].items()):
                f.write(f"{s},{lab},{cnt}\n")

    segments_csv = outp.with_suffix(".segments.csv")
    with open(segments_csv, "w", encoding="utf-8") as f:
        f.write("id,label,start_ms,end_ms,duration_ms,n_keyframes\n")
        for seg in segments:
            f.write(f"{seg['id']},{seg['label']},{seg['start_ms']},{seg['end_ms']},{seg['end_ms']-seg['start_ms']},{len(seg['keys'])}\n")

    log(f"[✓] Bitti → {args.out}")
    log(f"[→] Çizilen kutu adedi (frame-bazlı): {applied}")
    log(f"[→] Saniye özeti   : {seconds_csv}")
    log(f"[→] Segment özeti  : {segments_csv}")


if __name__ == "__main__":
    main()
