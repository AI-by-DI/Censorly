import uuid, datetime as dt, jwt
import jwt
from jwt import PyJWKClient
from passlib.context import CryptContext
from ..core.config import settings

_pwd = CryptContext(schemes=[settings.PASSWORD_SCHEME, "bcrypt"], deprecated="auto")

def hash_password(raw: str) -> str:
    return _pwd.hash(raw)

def verify_password(raw: str, hashed: str) -> bool:
    return _pwd.verify(raw, hashed)

def _claims(sub: str, typ: str, minutes: int = 0, days: int = 0):
    now = dt.datetime.now(dt.timezone.utc)
    exp = now + (dt.timedelta(minutes=minutes) if minutes else dt.timedelta(days=days))
    jti = str(uuid.uuid4())
    return {"iss": settings.JWT_ISSUER, "sub": sub, "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()), "jti": jti, "typ": typ}, exp, jti

def create_access_token(user_id: str | uuid.UUID, scopes: list[str] | None = None):
    sub = str(user_id)
    claims, exp, jti = _claims(sub, "access", minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    if scopes: claims["scopes"] = scopes
    token = jwt.encode(claims, settings.JWT_SECRET, algorithm="HS256")
    return token, exp, jti

def create_refresh_token(user_id: str | uuid.UUID):
    sub = str(user_id)
    claims, exp, jti = _claims(sub, "refresh", days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    token = jwt.encode(claims, settings.JWT_SECRET, algorithm="HS256")
    return token, exp, jti

def decode_token(token: str):
    if settings.AUTH_MODE == "oidc":
        # OIDC: sağlayıcının JWKS'inden imza doğrula
        jwks_client = PyJWKClient(settings.OIDC_JWKS_URL)
        signing_key = jwks_client.get_signing_key_from_jwt(token).key
        return jwt.decode(
            token, signing_key,
            algorithms=["RS256"],  # OIDC sağlayıcıları tipik olarak RS256
            audience=settings.OIDC_AUDIENCE,
            issuer=settings.OIDC_ISSUER,
            options={"require": ["exp", "sub"]}
        )
    # Local: mevcut HS256
    return jwt.decode(
        token, key=settings.JWT_SECRET,
        algorithms=["HS256"],
        options={"require": ["exp","jti","sub","typ"]}
    )