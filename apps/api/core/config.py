# apps/api/core/config.py
from __future__ import annotations
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    APP_NAME: str = "Censorly API"

    # --- DB: .env'de DATABASE_URL varsa onu kullan; yoksa postgres_* parçalarından kur ---
    DATABASE_URL: Optional[str] = None
    postgres_user: str = Field(default="censorly")
    postgres_password: str = Field(default="censorly")
    postgres_db: str = Field(default="censorly")
    postgres_host: str = Field(default="db")
    postgres_port: int = Field(default=5432)

    # --- Auth/JWT ---
    JWT_SECRET: str = Field(default="dev-secret-change-me")  # PROD'da mutlaka değiştir
    JWT_ISSUER: str = "censorly"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 45
    REFRESH_TOKEN_EXPIRE_DAYS: int = 21

    # --- Redis ---
    REDIS_URL: str = "redis://redis:6379/0"

    # --- Password / Auth mode ---
    PASSWORD_SCHEME: str = "argon2"
    AUTH_MODE: str = "local"   # "local" | "oidc"
    OIDC_ISSUER: str | None = None
    OIDC_JWKS_URL: str | None = None
    OIDC_AUDIENCE: str | None = None

    # --- (Opsiyonel) MinIO/S3 alanları; varsa env'den gelsin, yoksa defaultlar kullanılsın ---
    s3_endpoint: str = "http://minio:9000"
    s3_access_key: str = "minio"
    s3_secret_key: str = "minio12345"
    s3_bucket: str = "videos"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = Field(default=False)

    # pydantic-settings v2 tarzı konfig
    model_config = SettingsConfigDict(
        env_file=(
            "/app/configs/api.env",   # container içi olası yerler
            "/app/configs/.env",
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="allow",               # modelde tanımlı olmayan env key'leri hata olmasın
        case_sensitive=False,
    )

    # DATABASE_URL yoksa postgres_* ile kur ve alanın içine yaz (mevcut kullanım bozulmasın)
    def model_post_init(self, __context) -> None:  # pydantic v2
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )

settings = Settings()