from typing import Optional
from pydantic import BaseModel, EmailStr, Field

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    country: str | None = None
    birth_year: Optional[int] = Field(
        default=None, ge=1925, le=2025, description="Doğum yılı (1925–2025 arası)"
    )
class LoginIn(BaseModel):
    email: EmailStr
    password: str

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
