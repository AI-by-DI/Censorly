# api/schemas/preference.py
from typing import Dict, Optional, Literal
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

# Kullanıcı 7 kategoriden istediklerini sansürleyebilecek
# ve sansür tipi "blur" veya "skip" olacak.

RedactMode = Literal["blur", "skip", "warn"]

class PreferenceProfileBase(BaseModel):
    name: Optional[str] = "default"
    # true = sansürleme, false = sansürle
    allow_map: Dict[str, bool] = Field(default_factory=dict)
    # genel mod (hiçbir kategori özel seçilmemişse geçerli)
    mode: RedactMode = "blur"
    # kategoriye özel sansür tipi
    mode_map: Dict[str, Literal["blur", "skip"]] = Field(default_factory=dict)

class PreferenceProfileCreate(PreferenceProfileBase):
    pass

class PreferenceProfileUpdate(BaseModel):
    name: Optional[str] = None
    allow_map: Optional[Dict[str, bool]] = None
    mode: Optional[Literal["blur", "skip", "warn"]] = None
    mode_map: Optional[Dict[str, Literal["blur", "skip"]]] = None

class PreferenceProfileOut(PreferenceProfileBase):
    id: UUID
    updated_at: Optional[datetime] = None

class EffectiveModesOut(BaseModel):
    profile_id: UUID
    effective: Dict[str, Literal["blur", "skip", "none"]]
