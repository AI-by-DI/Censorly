# ai/inference/derive_dynamic_thresholds.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, json, pathlib
from collections import defaultdict
from dataclasses import dataclass, asdict, is_dataclass
from typing import Dict, List, Set, Any

def clamp(x, a, b): return max(a, min(b, x))

# ---------- JSON SAFE ----------
def json_safe(o: Any):
    if is_dataclass(o):
        return json_safe(asdict(o))
    if isinstance(o, dict):
        return {k: json_safe(v) for k, v in o.items()}
    if isinstance(o, set):
        return sorted(list(o))
    if isinstance(o, (list, tuple)):
        return [json_safe(v) for v in o]
    return o

# ---------- PRESET ----------
@dataclass
class Preset:
    label_family: Set[str]
    base: float
    tmin: float
    tmax: float
    hysteresis: float

    tpk_lo: float
    tpk_hi: float
    seen_thr: float

    alpha_down: float

    alpha_up: float
    prev_lo: float
    prev_mid: float

    bands: List[float]
    cuts:  List[float]

    env_labels: Set[str]
    env_cap: float

    g_power: float

    use_bucket_max_for_topk: bool
    int_thr: float

def presets_default() -> Dict[str, Preset]:
    # ⚠️ blood & alcohol presetleri DEĞİŞTİRİLMEDİ
    return {
        "blood": Preset(
            label_family={"blood"},
            base=0.25, tmin=0.15, tmax=0.35, hysteresis=0.05,
            tpk_lo=0.30, tpk_hi=0.60, seen_thr=0.30,
            alpha_down=0.10, alpha_up=0.00, prev_lo=0.00, prev_mid=0.00,
            bands=[0.25, 0.23, 0.20, 0.16],
            cuts =[0.24, 0.215, 0.18],
            env_labels=set(), env_cap=1.0,
            g_power=0.0,
            use_bucket_max_for_topk=False,
            int_thr=0.0
        ),
        "alcohol": Preset(
            label_family={
                "alcohol rack","beer bottle","beer can","beer glass",
                "champagne bottle","champagne glass","cocktail",
                "liquor bottle","liquor glass","vodka bottle","vodka glass",
                "whiskey bottle","whiskey glass","white wine glass",
                "wine bottle","wine glass"
            },
            base=0.45, tmin=0.35, tmax=0.55, hysteresis=0.05,
            tpk_lo=0.35, tpk_hi=0.65, seen_thr=0.45,
            alpha_down=0.10, alpha_up=0.10, prev_lo=0.08, prev_mid=0.25,
            bands=[0.55, 0.50, 0.45, 0.40, 0.35],
            cuts =[0.52, 0.475, 0.425, 0.375],
            env_labels={"alcohol rack"}, env_cap=0.40,
            g_power=1.0,
            use_bucket_max_for_topk=True,
            int_thr=-1.0
        ),
        # Diğer presetler kaldırıldı: script sadece blood & alcohol çalışır.
    }

# ---------- HELPERS ----------
def _to_int_safe(x: Any, default: int = 0) -> int:
    try:
        return int(round(float(x)))
    except Exception:
        return default

def bucket_of(obj) -> int:
    """
    Kovayı (yaklaşık saniye) belirle:
      - frame_idx varsa doğrudan al
      - ts_ms varsa ms→s çevir
      - ts / time / timestamp / t saniye cinsinden
    """
    if obj.get("frame_idx") is not None:
        return _to_int_safe(obj.get("frame_idx"), 0)

    # ms tabanlı alanlar
    for k in ("ts_ms", "time_ms", "timestamp_ms"):
        if obj.get(k) is not None:
            return _to_int_safe(float(obj[k]) / 1000.0, 0)

    # saniye tabanlı alanlar
    for k in ("ts", "time", "timestamp", "t"):
        if obj.get(k) is not None:
            return _to_int_safe(obj[k], 0)

    return 0

def quantize(x: float, bands: List[float], cuts: List[float]) -> float:
    if not bands: return x
    if (not cuts) or len(cuts) != len(bands)-1:
        return bands[-1]
    for i, c in enumerate(cuts):
        if x >= c:
            return bands[i]
    return bands[-1]

def compute_topk_mean(values: List[float], k:int=50, int_thr:float=0.0) -> float:
    vals = sorted(values, reverse=True)
    use = [v for v in vals if v >= int_thr] if int_thr>0 else vals
    if not use: use = vals
    k = min(k, len(use))
    return (sum(use[:k]) / k) if k>0 else 0.0

# ---------- CORE ----------
def run_for_class(jsonl_path: pathlib.Path, preset: Preset) -> Dict[str, Any]:
    fam = {s.lower() for s in preset.label_family}
    env = {s.lower() for s in preset.env_labels}
    by_bucket: Dict[int, List[float]] = defaultdict(list)

    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                obj=json.loads(line)
            except Exception:
                continue

            # tekil format
            lbl = (obj.get("label") or obj.get("cls") or obj.get("name") or "").lower()
            sc  = obj.get("score", obj.get("conf", None))
            if sc is not None and (lbl in fam or lbl in env):
                sc = float(sc)
                if lbl in env:
                    sc = min(sc, preset.env_cap)
                by_bucket[bucket_of(obj)].append(sc)
                continue

            # listeli format
            dets = obj.get("detections") or obj.get("objects") or []
            if dets:
                b = bucket_of(obj)
                for d in dets:
                    dlbl=(d.get("label") or d.get("cls") or d.get("name") or "").lower()
                    if (dlbl in fam) or (dlbl in env):
                        sc = float(d.get("score", d.get("conf", 0.0)))
                        if dlbl in env:
                            sc = min(sc, preset.env_cap)
                        by_bucket[b].append(sc)

    buckets = sorted(by_bucket.keys())
    if not buckets:
        on = clamp(preset.base, preset.tmin, preset.tmax)
        off= clamp(on + preset.hysteresis, preset.tmin, preset.tmax)
        return {
            "on": on, "off": off,
            "dominance": 0.0,
            "soft_prevalence": 0.0,
            "topk_mean": 0.0,
            "meta": {"reason":"no_hits", **json_safe(preset)}
        }

    # soft prevalence (bucket_max ile)
    bucket_max = [ (max(v) if v else 0.0) for _, v in sorted(by_bucket.items()) ]
    seen_thr = max(preset.base, preset.seen_thr)
    soft_prev = sum(1 for v in bucket_max if v >= seen_thr) / max(1, len(bucket_max))

    # top-k mean kaynağı
    if preset.use_bucket_max_for_topk:
        topk_source = bucket_max
    else:
        topk_source = [s for _, lst in sorted(by_bucket.items()) for s in lst]

    int_thr = seen_thr if preset.int_thr < 0 else preset.int_thr
    topk_mean = compute_topk_mean(topk_source, k=50, int_thr=int_thr)

    # sürücü g
    lo, hi = preset.tpk_lo, preset.tpk_hi
    if hi <= lo: hi = lo + 1e-6
    if topk_mean <= lo: g = 0.0
    elif topk_mean >= hi: g = 1.0
    else: g = (topk_mean - lo) / (hi - lo)

    # prevalansla frenleme
    g_eff = g * (soft_prev ** max(0.0, preset.g_power))

    # aşağı + yukarı adaptasyon
    on_raw = clamp(preset.base - preset.alpha_down * g_eff, preset.tmin, preset.tmax)
    if preset.alpha_up > 0.0:
        if soft_prev < preset.prev_lo:
            on_raw = max(on_raw, min(preset.tmax, preset.base + preset.alpha_up))
        elif soft_prev < preset.prev_mid and g < 0.30:
            on_raw = max(on_raw, min(preset.tmax, preset.base + 0.05))
    off_raw = clamp(on_raw + preset.hysteresis, preset.tmin, preset.tmax)

    # kademeli kuantizasyon
    on_q  = quantize(on_raw, preset.bands, preset.cuts)
    off_q = clamp(on_q + preset.hysteresis, preset.tmin, preset.tmax)

    return {
        "on": round(on_q, 3), "off": round(off_q, 3),
        "on_raw": round(on_raw, 4), "off_raw": round(off_raw, 4),
        "dominance": round(float(g_eff), 4),
        "soft_prevalence": round(soft_prev, 4),
        "topk_mean": round(topk_mean, 4),
        "meta": {**json_safe(preset), "seen_thr_eff": seen_thr, "int_thr_eff": int_thr}
    }

# ---------- CLI ----------
ALLOWED_CLASSES = {"blood", "alcohol"}

def build_argparser():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", required=True, help="analysis jsonl path")
    ap.add_argument("--out", required=True, help="output thresholds json")
    # Varsayılan artık SADECE blood & alcohol
    ap.add_argument("--classes", default="blood,alcohol",
                    help="comma-separated; only 'blood' and 'alcohol' are supported")
    ap.add_argument("--override", default="",
                    help='JSON string to override preset fields per class, e.g. {"alcohol":{"env_cap":0.35}}')
    ap.add_argument("--emit_min_score_map", action="store_true",
                    help="print a min_score_map string for pipeline_redact")
    return ap

def main():
    args = build_argparser().parse_args()
    jsonl_path = pathlib.Path(args.jsonl)
    assert jsonl_path.exists(), f"not found: {jsonl_path}"

    pres = presets_default()

    # Kullanıcının girdiği sınıfları al, yalnızca ALLOWED_CLASSES bırak
    wanted_raw = [s.strip().lower() for s in args.classes.split(",") if s.strip()]
    wanted = [c for c in wanted_raw if c in ALLOWED_CLASSES]
    ignored = [c for c in wanted_raw if c not in ALLOWED_CLASSES]
    if ignored:
        print(f"[info] ignored classes (only blood/alcohol supported): {', '.join(ignored)}")

    # Hiçbiri kalmadıysa default ikiliyi kullan
    if not wanted:
        wanted = ["blood", "alcohol"]

    # override destek
    if args.override:
        try:
            ov = json.loads(args.override)
            for cls_name, fields in ov.items():
                if cls_name in pres:
                    for f, val in fields.items():
                        if hasattr(pres[cls_name], f):
                            cur = getattr(pres[cls_name], f)
                            if isinstance(cur, set) and isinstance(val, list):
                                setattr(pres[cls_name], f, set(val))
                            else:
                                setattr(pres[cls_name], f, val)
        except Exception as e:
            print(f"[override ignored] {e}")

    results = {}
    for c in wanted:
        if c not in pres: 
            print(f"[warn] preset not found for class: {c}")
            continue
        results[c] = run_for_class(jsonl_path, pres[c])

    min_map = ", ".join([f"{c}:{results[c]['on']}" for c in results])

    out = {"thresholds": results, "min_score_map": min_map}
    pathlib.Path(args.out).write_text(json.dumps(json_safe(out), indent=2), encoding="utf-8")
    print(json.dumps(json_safe(out), indent=2))

    if args.emit_min_score_map:
        print(min_map)

if __name__ == "__main__":
    main()
