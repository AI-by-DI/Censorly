# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, json, pathlib, subprocess, shutil, os
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

import cv2, numpy as np

def log(*a):
    print(*a, flush=True)

# ----------------- arg parsing helpers -----------------

def parse_min_score_map(arg: str, fallback: float) -> Dict[str, float]:
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

def parse_labels(arg: str) -> Optional[List[str]]:
    return [s.strip() for s in arg.split(",") if s.strip()] if arg else None

# case-insensitive threshold lookup
def _ms_lookup(msmap: Dict[str, float], label: str, fallback: float) -> float:
    if label in msmap:
        return float(msmap[label])
    low = label.lower()
    for k, v in msmap.items():
        if k.lower() == low:
            return float(v)
    return float(msmap.get("default", fallback))

def emit_threshold_report(labs: Optional[List[str]], msmap: Dict[str, float], jsonl_path: str, global_fallback: float = 0.25):
    labels_to_report = (labs[:] if labs else [k for k in msmap.keys() if k.lower() != "default"])
    seen, uniq = set(), []
    for l in labels_to_report:
        if l.lower() not in seen:
            seen.add(l.lower())
            uniq.append(l)
    eff = {l: _ms_lookup(msmap, l, global_fallback) for l in uniq}
    log("[thresholds] Etkin eşikler:")
    w = max([len(s) for s in uniq] + [5])
    for l in uniq:
        log(f"  {l:<{w}} | thr={eff[l]:.3f}")
    if "default" in msmap:
        log(f"  {'(default)':<{w}} | thr={float(msmap['default']):.3f}")

    base = pathlib.Path(jsonl_path)
    base.with_suffix(".thresholds.json").write_text(
        json.dumps({"effective_thresholds": eff, "default": float(msmap.get("default", global_fallback))}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    base.with_suffix(".thresholds.txt").write_text(
        "\n".join([f"{l}\t{eff[l]:.3f}" for l in uniq] + ([f"default\t{float(msmap['default']):.3f}"] if "default" in msmap else [])),
        encoding="utf-8")
    log(f"[→] eşik raporları yazıldı: {base.with_suffix('.thresholds.json')} , {base.with_suffix('.thresholds.txt')}")

# ----------------- IO / parsing -----------------

def load_events(jsonl_path: str,
                wanted_lower: Optional[set],
                min_score_map: Dict[str, float]) -> List[dict]:
    evs: List[dict] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            e = json.loads(s)
            lab = str(e.get("label", "")).strip()
            raw = e.get("raw_label")
            raw = str(raw).strip() if raw else None
            # phobic ise ve raw varsa raw'ı label yap
            eff_lab = raw if (lab.lower() == "phobic" and raw) else lab

            if wanted_lower and eff_lab.lower() not in wanted_lower:
                continue

            ms = _ms_lookup(min_score_map, eff_lab, fallback=0.25)
            sc = float(e.get("score", 0.0))
            if sc < ms:
                continue

            bbox = e.get("bbox")
            if not bbox:
                continue

            e["ts_ms"] = int(e["ts_ms"])
            e["label"] = eff_lab
            evs.append(e)

    evs.sort(key=lambda x: (x["label"], x["ts_ms"]))
    log(f"[i] JSONL yüklendi: {jsonl_path} (filtre sonrası {len(evs)} satır)")
    return evs

# ----------------- geometry & metrics -----------------

def yolo_bbox_to_xyxy(bbox: List[float], W: int, H: int) -> Tuple[int, int, int, int]:
    cx, cy, w, h = bbox
    x1 = int(round((cx - w / 2) * W)); y1 = int(round((cy - h / 2) * H))
    x2 = int(round((cx + w / 2) * W)); y2 = int(round((cy + h / 2) * H))
    x1 = max(0, min(W - 1, x1)); y1 = max(0, min(H - 1, y1))
    x2 = max(0, min(W - 1, x2)); y2 = max(0, min(H - 1, y2))
    if x2 < x1: x1, x2 = x2, x1
    if y2 < y1: y1, y2 = y2, y1
    return x1, y1, x2, y2

def bbox_iou(b1: List[float], b2: List[float]) -> float:
    def to_xyxy(b):
        cx, cy, w, h = b
        return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    ax1, ay1, ax2, ay2 = to_xyxy(b1); bx1, by1, bx2, by2 = to_xyxy(b2)
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    aw, ah = (ax2 - ax1), (ay2 - ay1)
    bw, bh = (bx2 - bx1), (by2 - by1)
    union = aw * ah + bw * bh - inter + 1e-9
    return inter / union

def center_dist(b1: List[float], b2: List[float]) -> float:
    return ((b1[0] - b2[0]) ** 2 + (b1[1] - b2[1]) ** 2) ** 0.5

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
    segs: List[dict] = []
    next_id = 1
    by_label: Dict[str, Dict[int, List[dict]]] = defaultdict(lambda: defaultdict(list))
    for e in events:
        by_label[e["label"]][e["ts_ms"]].append(e)

    for lab, ts_map in by_label.items():
        active: List[dict] = []
        for ts in sorted(ts_map.keys()):
            detections = ts_map[ts]
            assigned = set(); used_segments = set()

            for d_idx, e in enumerate(detections):
                best_j = -1; best_score = -1.0
                for j, seg in enumerate(active):
                    if j in used_segments: continue
                    last_ts, last_bbox, _ = seg["keys"][-1]
                    if ts - last_ts > hold_gap_ms: continue
                    iou = bbox_iou(e["bbox"], last_bbox)
                    dist = center_dist(e["bbox"], last_bbox)
                    score = iou - 0.1 * dist
                    if iou < iou_thr and dist > max_center_dist: continue
                    if score > best_score:
                        best_score = score; best_j = j
                if best_j >= 0:
                    seg = active[best_j]
                    seg["keys"].append((ts, e["bbox"], float(e.get("score", 0.0))))
                    seg["end_ms"] = ts + grace_ms
                    used_segments.add(best_j); assigned.add(d_idx)

            for d_idx, e in enumerate(detections):
                if d_idx in assigned: continue
                seg = {
                    "id": f"{lab}-{next_id}",
                    "label": lab,
                    "start_ms": e["ts_ms"],
                    "end_ms": e["ts_ms"] + grace_ms,
                    "keys": [(e["ts_ms"], e["bbox"], float(e.get("score", 0.0)))],
                }
                active.append(seg); next_id += 1

            still_active = []
            for seg in active:
                last_ts = seg["keys"][-1][0]
                if ts - last_ts <= hold_gap_ms:
                    still_active.append(seg)
                else:
                    segs.append(seg)
            active = still_active

        for seg in active:
            segs.append(seg)

    segs.sort(key=lambda s: (s["start_ms"], s["label"], s["id"]))
    log(f"[i] segment sayısı (multi-instance): {len(segs)}")
    return segs

def bbox_at_time(seg: dict, t_ms: int) -> Optional[Tuple[List[float], float]]:
    keys = seg["keys"]
    if not keys: return None
    if t_ms < seg["start_ms"] or t_ms > seg["end_ms"]: return None
    if len(keys) == 1: return keys[0][1], keys[0][2]
    for i in range(len(keys) - 1):
        t0, b0, s0 = keys[i]; t1, b1, s1 = keys[i + 1]
        if t_ms <= t1:
            b = interp_bbox(t_ms, t0, b0, t1, b1)
            alpha = 0.0 if t1 == t0 else (t_ms - t0) / max(1, (t1 - t0))
            s = lerp(s0, s1, alpha)
            return b, s
    return keys[-1][1], keys[-1][2]

# ----------------- drawing -----------------

def draw_red_box_outline(img, x1, y1, x2, y2, label, score, seg_id=None, thick=3, put_inside=True):
    if x2 <= x1 or y2 <= y1: return
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), thickness=thick)
    tag_full = f"{label} {score:.2f}" + (f" [{seg_id}]" if seg_id else "")
    font = cv2.FONT_HERSHEY_SIMPLEX
    bw, bh = (x2 - x1), (y2 - y1); pad = max(4, thick + 1)
    max_w = max(10, bw - 2 * pad); max_h = max(10, bh - 2 * pad)
    font_scale = 0.7; font_thick = 2
    def text_size(txt, fs, ft): (tw, th), _ = cv2.getTextSize(txt, font, fs, ft); return tw, th
    tw, th = text_size(tag_full, font_scale, font_thick)
    tries = 0; tag = tag_full
    while (tw > max_w or th > max_h) and tries < 10:
        font_scale *= 0.85
        if font_thick > 1 and tries >= 2: font_thick -= 1
        tw, th = text_size(tag, font_scale, font_thick); tries += 1
    if tw > max_w or th > max_h:
        short_label = (label[:8] + "…") if len(label) > 9 else label
        tag = f"{short_label} {score:.2f}"
        font_scale = max(0.4, font_scale * 0.9)
        tw, th = text_size(tag, font_scale, font_thick)
    if put_inside and tw <= max_w and th <= max_h:
        tx = x1 + pad; ty = y1 + pad + th
        bg_x1, bg_y1 = tx - 2, ty - th - 4; bg_x2, bg_y2 = min(x2, tx + tw + 2), min(y2, ty + 4)
        overlay = img.copy()
        cv2.rectangle(overlay, (bg_x1, max(y1, bg_y1)), (bg_x2, bg_y2), (0, 0, 180), -1)
        cv2.addWeighted(overlay, 0.55, img, 0.45, 0)
        cv2.putText(img, tag, (tx, ty), font, font_scale, (255, 255, 255), font_thick, cv2.LINE_AA)
    else:
        (tw, th), _ = cv2.getTextSize(tag, font, 0.6, 2)
        yb1 = max(0, y1 - th - 8)
        cv2.rectangle(img, (x1, yb1), (x1 + tw + 8, y1), (0, 0, 200), thickness=-1)
        cv2.putText(img, tag, (x1 + 4, y1 - 5), font, 0.6, (255, 255, 255), 2, cv2.LINE_AA)

def draw_blur_box(img, x1, y1, x2, y2, ksize=35):
    if x2 <= x1 or y2 <= y1: return
    k = max(3, ksize | 1)
    roi = img[y1:y2, x1:x2]
    if roi.size == 0: return
    img[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (k, k), 0)

# ----------------- audio mux (ffmpeg) -----------------

def mux_audio_with_ffmpeg(video_no_audio: pathlib.Path, audio_src: pathlib.Path, final_out: pathlib.Path, ffmpeg_path: str = "ffmpeg") -> bool:
    if shutil.which(ffmpeg_path) is None:
        log(f"[warn] ffmpeg bulunamadı ({ffmpeg_path}). Ses eklenemedi.")
        return False
    cmd = [
        ffmpeg_path, "-y",
        "-i", str(video_no_audio),
        "-i", str(audio_src),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac",
        "-shortest", str(final_out),
    ]
    log("[ffmpeg] ", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            log("[ffmpeg][stderr]\n", proc.stderr.decode(errors="ignore"))
            log("[ffmpeg] hata kodu:", proc.returncode)
            return False
        return True
    except Exception as e:
        log("[ffmpeg] hata:", e)
        return False

# ----------------- main -----------------

def main():
    ap = argparse.ArgumentParser(description="Multi-instance temporal redaction with per-label modes (blur/red/skip).")
    ap.add_argument("--video", required=True)
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--out", required=True)

    # Yeni: per-kova label listeleri
    ap.add_argument("--labels_blur", type=str, default="")
    ap.add_argument("--labels_red",  type=str, default="")
    ap.add_argument("--labels_skip", type=str, default="")

    # Geriye dönük uyum (tek liste & tek mod)
    ap.add_argument("--labels", default="", help="legacy")
    ap.add_argument("--mode", choices=["red", "blur"], default="blur", help="legacy global mode")

    ap.add_argument("--min_score", type=float, default=0.5)
    ap.add_argument("--min_score_map", type=str, default="")
    ap.add_argument("--hold_gap_ms", type=int, default=600)
    ap.add_argument("--grace_ms", type=int, default=200)
    ap.add_argument("--iou_thr", type=float, default=0.1)
    ap.add_argument("--max_center_dist", type=float, default=0.25)
    ap.add_argument("--blur_k", type=int, default=35)
    ap.add_argument("--box_thick", type=int, default=3)
    ap.add_argument("--min_keyframes_map", type=str, default="default:2")
    ap.add_argument("--min_skip_ms", type=int, default=2000, help="skip için minimum segment süresi (ms)")

    # Audio
    ap.add_argument("--keep_audio", action="store_true")
    ap.add_argument("--audio_src", type=str, default="")
    ap.add_argument("--ffmpeg_path", type=str, default="ffmpeg")

    # Dinamik eşik
    ap.add_argument("--thresholds_json", type=str, default="")
    ap.add_argument("--dyn_from_json", type=str, default="blood,alcohol")

    args = ap.parse_args()

    # label kovaları
    blur_labs = parse_labels(args.labels_blur) or []
    red_labs  = parse_labels(args.labels_red)  or []
    skip_labs = parse_labels(args.labels_skip) or []

    # legacy desteği
    if not (blur_labs or red_labs or skip_labs):
        legacy = parse_labels(args.labels) or []
        if args.mode == "red": red_labs = legacy
        else: blur_labs = legacy

    union_labs = sorted(list(dict.fromkeys(blur_labs + red_labs + skip_labs)))

    msmap = parse_min_score_map(args.min_score_map, args.min_score)
    _mkf = parse_min_score_map(args.min_keyframes_map, 1.0)
    min_keyframes_map: Dict[str, int] = {k: int(v) for k, v in _mkf.items()}

    # thresholds_json uygula (isteğe bağlı)
    if args.thresholds_json:
        try:
            p = pathlib.Path(args.thresholds_json)
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                thr = (data.get("thresholds") or {})
                wanted_dyn = {s.strip().lower() for s in (args.dyn_from_json or "").split(",") if s.strip()}
                updated = {}
                for lab in wanted_dyn:
                    node = thr.get(lab)
                    if isinstance(node, dict) and ("on" in node):
                        try:
                            on_val = float(node["on"])
                            msmap[lab] = on_val
                            updated[lab] = round(on_val, 3)
                        except Exception:
                            pass
                if "default" not in msmap:
                    msmap["default"] = args.min_score
                if updated:
                    log(f"[dyn] thresholds_json uygulandı → {args.thresholds_json} | dyn_from_json={sorted(list(wanted_dyn))} | güncellenen={updated}")
                else:
                    log(f"[dyn][info] thresholds_json okundu fakat güncellenecek etiket bulunamadı. dyn_from_json={sorted(list(wanted_dyn))}")
            else:
                log(f"[dyn][warn] thresholds_json bulunamadı: {p}")
        except Exception as e:
            log(f"[dyn][warn] thresholds_json okunamadı: {e}")

    log("[cfg] labels_blur=", blur_labs, "labels_red=", red_labs, "labels_skip=", skip_labs,
        "min_score_map=", msmap, "min_skip_ms=", args.min_skip_ms,
        "hold_gap_ms=", args.hold_gap_ms, "grace_ms=", args.grace_ms,
        "blur_k=", args.blur_k, "min_keyframes_map=", min_keyframes_map,
        "keep_audio=", args.keep_audio, "audio_src=", args.audio_src or "<video>")

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    log(f"[i] video info: {W}x{H} @ {fps:.3f} fps")

    emit_threshold_report(union_labs, msmap, args.jsonl, global_fallback=0.25)

    want_lower = {s.lower() for s in union_labs} if union_labs else None
    events = load_events(args.jsonl, want_lower, msmap)
    segments = build_segments_multi(events, args.hold_gap_ms, args.grace_ms, args.iou_thr, args.max_center_dist)

    # segment kovaları
    seg_blur, seg_red, seg_skip = [], [], []
    blur_set, red_set, skip_set = set([l.lower() for l in blur_labs]), set([l.lower() for l in red_labs]), set([l.lower() for l in skip_labs])
    for s in segments:
        ll = s["label"].lower()
        if ll in skip_set: seg_skip.append(s)
        elif ll in red_set: seg_red.append(s)
        elif ll in blur_set: seg_blur.append(s)

    # keyframe filtresi
    def _keep(seg: dict) -> bool:
        need = min_keyframes_map.get(seg["label"], min_keyframes_map.get("default", 2))
        return len(seg["keys"]) >= max(1, int(need))
    b0, r0, k0 = len(seg_blur), len(seg_red), len(seg_skip)
    seg_blur = [s for s in seg_blur if _keep(s)]
    seg_red  = [s for s in seg_red  if _keep(s)]
    seg_skip = [s for s in seg_skip if _keep(s)]
    log(f"[i] keyframe filtresi: blur {b0}->{len(seg_blur)} | red {r0}->{len(seg_red)} | skip {k0}->{len(seg_skip)}")

    # skip aralıklarını birleştir & min süre uygula
    def _merge_and_thresh(ss: List[dict], min_ms: int) -> List[Tuple[int,int]]:
        if not ss: return []
        ivs = sorted([(s["start_ms"], s["end_ms"]) for s in ss])
        out = []
        cur_s, cur_e = ivs[0]
        for s,e in ivs[1:]:
            if s <= cur_e: cur_e = max(cur_e, e)
            else:
                if cur_e - cur_s >= min_ms: out.append((cur_s, cur_e))
                cur_s, cur_e = s, e
        if cur_e - cur_s >= min_ms: out.append((cur_s, cur_e))
        return out

    skip_intervals = _merge_and_thresh(seg_skip, args.min_skip_ms)
    if skip_intervals:
        log(f"[skip] uygulanacak aralıklar (ms): {skip_intervals}")
        if args.keep_audio:
            log("[skip][warn] skip aktif → keep_audio devre dışı bırakılıyor (ileride senkron kesim eklenecek).")
        keep_audio = False
    else:
        keep_audio = bool(args.keep_audio)

    # writer
    out_final = pathlib.Path(args.out)
    if keep_audio:
        out_noaudio = out_final.with_name(out_final.stem + "_noaudio" + out_final.suffix)
        target_path_for_writer = out_noaudio
    else:
        target_path_for_writer = out_final

    def open_writer(path: str):
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        vw = cv2.VideoWriter(path, fourcc, fps, (W, H))
        if vw.isOpened(): return vw
        fourcc = cv2.VideoWriter_fourcc(*"avc1")
        return cv2.VideoWriter(path, fourcc, fps, (W, H))

    out = open_writer(str(target_path_for_writer))
    if not out or not out.isOpened():
        raise RuntimeError(f"Cannot open writer: {target_path_for_writer}")

    # hızlı aralık testi için
    def in_skip(ts: int) -> bool:
        if not skip_intervals: return False
        # aralık sayısı az olacağından lineer kontrol yeter
        for s,e in skip_intervals:
            if s <= ts <= e: return True
        return False

    frame_idx = 0
    applied = 0
    secs = defaultdict(lambda: defaultdict(int))

    while True:
        ok, frame = cap.read()
        if not ok: break
        ts_ms = int(round(frame_idx * 1000.0 / fps))
        frame_idx += 1

        # skip aralığındaysa frame'i yazma
        if in_skip(ts_ms): 
            continue

        # red/blur çizimleri
        for seg in seg_red:
            if seg["start_ms"] <= ts_ms <= seg["end_ms"]:
                bb = bbox_at_time(seg, ts_ms)
                if not bb: continue
                bbox_norm, score = bb
                x1, y1, x2, y2 = yolo_bbox_to_xyxy(bbox_norm, W, H)
                draw_red_box_outline(frame, x1, y1, x2, y2, seg["label"], float(score), seg_id=seg["id"], thick=int(args.box_thick))
                applied += 1; secs[ts_ms//1000][seg["label"]] += 1

        for seg in seg_blur:
            if seg["start_ms"] <= ts_ms <= seg["end_ms"]:
                bb = bbox_at_time(seg, ts_ms)
                if not bb: continue
                bbox_norm, score = bb
                x1, y1, x2, y2 = yolo_bbox_to_xyxy(bbox_norm, W, H)
                draw_blur_box(frame, x1, y1, x2, y2, ksize=int(args.blur_k))
                applied += 1; secs[ts_ms//1000][seg["label"]] += 1

        out.write(frame)
        if frame_idx % 100 == 0:
            log(f"[prog] frame={frame_idx} applied_boxes={applied}")

    cap.release()
    out.release()

    # Audio mux (skip yoksa)
    if keep_audio:
        audio_src = pathlib.Path(args.audio_src) if args.audio_src else pathlib.Path(args.video)
        ok = mux_audio_with_ffmpeg(target_path_for_writer, audio_src, out_final, ffmpeg_path=args.ffmpeg_path)
        if ok:
            try: os.remove(target_path_for_writer)
            except Exception: pass
            log(f"[✓] Ses eklendi → {out_final}")
        else:
            log(f"[warn] Ses eklenemedi. Sessiz çıktı tutuldu: {target_path_for_writer}")
    else:
        log(f"[i] Ses ekleme yok (skip aktif olabilir). Çıktı: {out_final}")

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
        for seg in (seg_red + seg_blur + seg_skip):
            f.write(f"{seg['id']},{seg['label']},{seg['start_ms']},{seg['end_ms']},{seg['end_ms']-seg['start_ms']},{len(seg['keys'])}\n")

    log(f"[✓] Bitti → {args.out}")
    log(f"[→] Çizilen kutu adedi (frame-bazlı): {applied}")
    log(f"[→] Saniye özeti   : {seconds_csv}")
    log(f"[→] Segment özeti  : {segments_csv}")

if __name__ == "__main__":
    main()
