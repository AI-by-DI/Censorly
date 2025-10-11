from pydantic import BaseModel, EmailStr
from datetime import datetime
from uuid import UUID

class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    country: str | None = None
    birth_year: int | None = None
    created_at: datetime
    updated_at: datetime
