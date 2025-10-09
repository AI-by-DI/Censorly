from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "Censorly API"
    DATABASE_URL: str
    JWT_SECRET: str
    JWT_ISSUER: str = "censorly"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 21
    REDIS_URL: str = "redis://redis:6379/0"
    PASSWORD_SCHEME: str = "argon2"
    AUTH_MODE: str = "local"   # "local" | "oidc"
    OIDC_ISSUER: str | None = None
    OIDC_JWKS_URL: str | None = None
    OIDC_AUDIENCE: str | None = None

    class Config:
        env_file = ".env"

settings = Settings()
