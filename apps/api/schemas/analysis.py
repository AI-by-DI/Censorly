# apps/api/schemas/analysis.py
from __future__ import annotations
from typing import List, Optional, Dict, Any, Literal, Union
from pydantic import BaseModel, Field, conlist, confloat

# Pipeline’dan gelen tekil detection kaydı
class DetectionIn(BaseModel):
    ts_ms: int = Field(ge=0)
    label: str  # 'alcohol' | 'blood' | 'violence' | 'phobic' | 'obscene' + alt etiketler zaten extra.raw_label'da
    score: confloat(ge=0.0, le=1.0)
    # bbox bazen [x, y, w, h], bazen dict olabilir; ikisini de kabul edelim
    bbox: Optional[Union[conlist(float, min_length=4, max_length=4), Dict[str, float]]] = None
    track_id: Optional[int] = None
    extra: Dict[str, Any] = Field(default_factory=dict)

# /analysis/jobs/{id}/ingest gövdesi
class IngestPayload(BaseModel):
    detections: List[DetectionIn] = Field(default_factory=list)

# /analysis/jobs/{id}/start gövdesi (şimdilik boş)
class JobStartPayload(BaseModel):
    pass

# /analysis/jobs/{id}/finish gövdesi
class JobFinishPayload(BaseModel):
    status: Literal["done", "failed"] = "done"