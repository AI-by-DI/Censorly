# apps/api/repositories/preference_repo.py
from typing import Optional, Dict, List
from uuid import UUID
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import JSONB
import json


def json_dumps(o): 
    return json.dumps(o, separators=(",", ":"))

# Listeleme
def list_profiles(db: Session, user_id: UUID) -> List[dict]:
    q = text("""
      SELECT id, user_id, name, mode, allow_map, mode_map, updated_at
      FROM preference_profiles
      WHERE user_id = :uid
      ORDER BY name ASC
    """)
    rows = db.execute(q, {"uid": str(user_id)}).mappings().all()
    return [dict(r) for r in rows]

# Tek kayıt
def get_profile(db: Session, user_id: UUID, profile_id: UUID) -> Optional[dict]:
    q = text("""
      SELECT id, user_id, name, mode, allow_map, mode_map, updated_at
      FROM preference_profiles
      WHERE user_id = :uid AND id = :pid
      LIMIT 1
    """)
    r = db.execute(q, {"uid": str(user_id), "pid": str(profile_id)}).mappings().first()
    return dict(r) if r else None

# Oluşturma
def create_profile(db: Session, user_id: UUID, payload: dict) -> dict:
    allow_map = payload.get("allow_map") or {}
    mode_map  = payload.get("mode_map")  or {}

    stmt = text("""
        INSERT INTO preference_profiles (id, user_id, name, mode, allow_map, mode_map)
        VALUES (gen_random_uuid(), :uid, :name, :mode, :allow_map, :mode_map)
        RETURNING id, user_id, name, mode, allow_map, mode_map, updated_at
    """).bindparams(
        bindparam("allow_map", type_=JSONB),
        bindparam("mode_map",  type_=JSONB),
    )

    params = {
        "uid": str(user_id),
        "name": payload.get("name", "default"),
        "mode": payload.get("mode", "blur"),
        "allow_map": allow_map,   # dict olarak gönderiyoruz
        "mode_map":  mode_map,    # dict olarak gönderiyoruz
    }
    row = db.execute(stmt, params).mappings().first()
    db.commit()
    return dict(row)

def update_profile(db: Session, user_id: UUID, profile_id: UUID, payload: dict) -> Optional[dict]:
    sets = []
    params = {"uid": str(user_id), "pid": str(profile_id)}
    needs_jsonb = {"allow_map": False, "mode_map": False}

    if "name" in payload:
        sets.append("name = :name")
        params["name"] = payload["name"]

    if "mode" in payload:
        sets.append("mode = :mode")
        params["mode"] = payload["mode"]

    if "allow_map" in payload:
        sets.append("allow_map = :allow_map")
        params["allow_map"] = payload["allow_map"] or {}
        needs_jsonb["allow_map"] = True

    if "mode_map" in payload:
        sets.append("mode_map = :mode_map")
        params["mode_map"] = payload["mode_map"] or {}
        needs_jsonb["mode_map"] = True

    if not sets:
        # değişiklik yoksa mevcut kaydı döndür
        return get_profile(db, user_id, profile_id)

    sql = f"""
        UPDATE preference_profiles
        SET {", ".join(sets)}, updated_at = NOW()
        WHERE user_id = :uid AND id = :pid
        RETURNING id, user_id, name, mode, allow_map, mode_map, updated_at
    """
    stmt = text(sql)
    # JSONB tipini bind et
    if needs_jsonb["allow_map"]:
        stmt = stmt.bindparams(bindparam("allow_map", type_=JSONB))
    if needs_jsonb["mode_map"]:
        stmt = stmt.bindparams(bindparam("mode_map", type_=JSONB))

    row = db.execute(stmt, params).mappings().first()
    db.commit()
    return dict(row) if row else None


# Etkin mod hesaplama (Python tarafı)
def compute_effective_modes(row: dict) -> Dict[str, str]:
    allow_map = row.get("allow_map") or {}
    mode_map  = row.get("mode_map")  or {}
    global_mode = row.get("mode") or "blur"

    cats = set(allow_map.keys()) | set(mode_map.keys())
    effective = {}
    for cat in cats:
        allow = allow_map.get(cat, True)
        if allow is True:
            effective[cat] = "none"
        else:
            effective[cat] = mode_map.get(cat, global_mode)
    return effective

# küçük yardımcı
import json
def json_dumps(o): return json.dumps(o, separators=(",", ":"))
