# apps/api/schemas/redaction.py
from __future__ import annotations
from typing import Optional, Dict, List
from pydantic import BaseModel, Field

class RenderRequest(BaseModel):
    profile_id: Optional[str] = Field(default=None)
    force: bool = False  # ileride cache'i kırmak için kullanılabilir

class RenderResult(BaseModel):
    ok: bool = True
    cached: bool
    profile_hash: str
    storage_key: str
    stream_url: Optional[str] = None
    plan_id: Optional[str] = None
    output_id: Optional[str] = None