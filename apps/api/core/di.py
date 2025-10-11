# apps/api/core/di.py
from fastapi import Depends
from sqlalchemy.orm import Session
import redis

from ..core.config import settings
from ..core.db import get_db
from ..repositories.user_repo import UserRepo

_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

def get_redis():
    return _redis

def get_user_repo(db: Session = Depends(get_db)) -> UserRepo:
    return UserRepo(db)
