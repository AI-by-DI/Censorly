# apps/api/utils/labels.py
from __future__ import annotations
from typing import Tuple, Dict, Any

_PHOBIC_CANON = {"clown": "Clown", "spider": "Spider", "snake": "Snake"}
_PHOBIC_CANON_SET = set(_PHOBIC_CANON.values())

def canon_phobic_name(s: str | None) -> str | None:
    if not s:
        return None
    s = str(s).strip().lower()
    if s.startswith("phobic/"):
        s = s.split("/", 1)[-1]
    return _PHOBIC_CANON.get(s)

def norm_label(label: str, extra: Dict[str, Any] | None) -> Tuple[str, Dict[str, Any]]:
    """JSONL/ingest’ten gelen etiketi kanonik hale getirir."""
    extra = (extra or {}).copy()
    raw = extra.get("raw_label") or extra.get("rawLabel") or extra.get("subtype")

    # 1) Analyzer direkt Clown/Spider/Snake verirse
    if label in _PHOBIC_CANON_SET:
        extra.setdefault("raw_label", label)
        return label, extra

    # 2) phobic/xxx ya da küçük harf varyantları
    by_label = canon_phobic_name(label)
    if by_label:
        extra.setdefault("raw_label", by_label)
        return by_label, extra

    # 3) ekstra’dan yakala
    by_extra = canon_phobic_name(raw)
    if by_extra:
        extra.setdefault("raw_label", by_extra)
        return by_extra, extra

    # 4) nudity/obscene ↦ nudenet
    low = (label or "").strip().lower()
    if low in ("nudity", "obscene", "nudenet"):
        return "nudenet", extra

    return label, extra
