from fastapi import APIRouter, Depends,Query,Form,Body, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, OAuth2PasswordBearer
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from sqlalchemy import text
from ..core.db import get_db
from ..core.di import get_user_repo, get_redis
from ..repositories.user_repo import UserRepo
from ..schemas.auth import RegisterIn, LoginIn, TokenPair
from ..schemas.user import UserOut
from ..services.auth_service import hash_password, verify_password, create_access_token, create_refresh_token, decode_token

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")
auth_scheme = HTTPBearer(auto_error=False)

def _ensure_not_blacklisted(redis, jti: str):
    if redis.sismember("jwt:blacklist", jti):
        raise HTTPException(status_code=401, detail="token_revoked")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(auth_scheme),
    db: Session = Depends(get_db),
    redis=Depends(get_redis),
) -> UserOut:
    token = credentials.credentials
    payload = decode_token(token)
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid_token")
    if payload.get("typ") != "access":
        raise HTTPException(status_code=401, detail="wrong_token_type")
    _ensure_not_blacklisted(redis, payload["jti"])
    row = db.execute(
        text("SELECT id,email,country,birth_year,created_at,updated_at FROM users WHERE id=:id"),
        {"id": payload["sub"]}
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=401, detail="user_not_found")
    return UserOut(**dict(row))

# (basit rate-limit)
import time
def ratelimit(redis, key: str, limit:int=5, window:int=60):
    now = int(time.time())
    p = redis.pipeline()
    p.incr(key, 1); p.expire(key, window)
    count, _ = p.execute()
    if count > limit:
        raise HTTPException(status_code=429, detail="too_many_attempts")

@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db), repo: UserRepo = Depends(get_user_repo)):
    if repo.get_by_email(body.email):
        raise HTTPException(status_code=400, detail="email_in_use")
    user = repo.create_user(body.email, hash_password(body.password), body.country, body.birth_year)
    return UserOut(**user)

@router.post("/login", response_model=TokenPair)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db), repo: UserRepo = Depends(get_user_repo), redis=Depends(get_redis)):
    ratelimit(redis, f"rl:login:{request.client.host}:{body.email}")
    user = repo.get_by_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid_credentials")
    access, _, _ = create_access_token(user["id"])
    refresh, ref_exp, ref_jti = create_refresh_token(user["id"])
    repo.store_refresh_jti(ref_jti, user["id"], ref_exp)
    return TokenPair(access_token=access, refresh_token=refresh)

@router.post("/refresh", response_model=TokenPair)
def refresh_token(token: str, db: Session = Depends(get_db), repo: UserRepo = Depends(get_user_repo)):
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid_token")
    if payload.get("typ") != "refresh":
        raise HTTPException(status_code=401, detail="wrong_token_type")
    jti = payload["jti"]
    if not repo.refresh_exists(jti):
        raise HTTPException(status_code=401, detail="refresh_revoked")
    user_id = payload["sub"]
    repo.revoke_refresh_jti(jti)
    access, _, _ = create_access_token(user_id)
    refresh, ref_exp, ref_jti = create_refresh_token(user_id)
    repo.store_refresh_jti(ref_jti, user_id, ref_exp)
    return TokenPair(access_token=access, refresh_token=refresh)

@router.get("/me", response_model=UserOut)
def me(current: UserOut = Depends(get_current_user)):
    return current

@router.post("/logout", status_code=204)
def logout(
    # 1) Öncelik: Authorization: Bearer <access>
    credentials: HTTPAuthorizationCredentials | None = Depends(auth_scheme),

    # 2) Geriye dönük uyumluluk: query
    access_token_q: str | None = Query(None),
    refresh_token_q: str | None = Query(None),

    # 3) Alternatif: form/json body
    access_token_f: str | None = Form(None),
    refresh_token_f: str | None = Form(None),
    access_token_b: str | None = Body(None, embed=True),
    refresh_token_b: str | None = Body(None, embed=True),

    redis = Depends(get_redis),
    db: Session = Depends(get_db),
    repo: UserRepo = Depends(get_user_repo),
):
    # access_token kaynaklarını sırayla dene (header > body > form > query)
    access_token = (
        (credentials.credentials if credentials else None)
        or access_token_b
        or access_token_f
        or access_token_q
    )
    refresh_token = refresh_token_b or refresh_token_f or refresh_token_q

    if not access_token:
        raise HTTPException(status_code=422, detail="access_token_required")

    # access token'ı blacklist et
    try:
        acc = decode_token(access_token)
        redis.sadd("jwt:blacklist", acc["jti"])
        ttl = acc["exp"] - acc["iat"]
        redis.expire("jwt:blacklist", ttl)
    except Exception:
        pass

    # refresh varsa revoke et
    if refresh_token:
        try:
            ref = decode_token(refresh_token)
            if ref.get("typ") == "refresh":
                repo.revoke_refresh_jti(ref["jti"])
        except Exception:
            pass
    return