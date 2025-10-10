# api/routers/preferences.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

# ⬇️ RELATIVE importlar
from ..schemas.preference import (
    PreferenceProfileOut,
    PreferenceProfileCreate,
    PreferenceProfileUpdate,
    EffectiveModesOut,
)
from ..repositories import preference_repo as repo
from ..core.db import get_db
from .auth import get_current_user  

router = APIRouter(prefix="/me/preferences", tags=["preferences"])

@router.get("", response_model=list[PreferenceProfileOut])
def list_my_profiles(db: Session = Depends(get_db), user=Depends(get_current_user)):
    items = repo.list_profiles(db, user.id)
    return items

@router.post("", response_model=PreferenceProfileOut, status_code=status.HTTP_201_CREATED)
def create_my_profile(payload: PreferenceProfileCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    existing = [p for p in repo.list_profiles(db, user.id) if p["name"] == (payload.name or "default")]
    if existing:
        raise HTTPException(status_code=409, detail="A profile with the same name already exists.")
    created = repo.create_profile(db, user.id, payload.model_dump())
    return created

@router.put("/{profile_id}", response_model=PreferenceProfileOut)
def update_my_profile(profile_id: UUID, payload: PreferenceProfileUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    updated = repo.update_profile(db, user.id, profile_id, payload.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Profile not found")
    return updated

@router.get("/{profile_id}/effective", response_model=EffectiveModesOut)
def get_effective_modes(profile_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    row = repo.get_profile(db, user.id, profile_id)
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"profile_id": row["id"], "effective": repo.compute_effective_modes(row)}
