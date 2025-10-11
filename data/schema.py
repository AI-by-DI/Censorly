# data/schema.py
from __future__ import annotations
import os
import uuid
from enum import Enum

from sqlalchemy import (
    create_engine, Column, String, Integer, Float, Numeric, Boolean, DateTime,
    ForeignKey, Enum as SAEnum, JSON, Index, CheckConstraint, UniqueConstraint, func, Text,
    text as sa_text
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.dialects.postgresql import JSONB as PGJSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# --- DB setup ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

# --- Dialect-aware helpers ---
is_postgres = DATABASE_URL.startswith("postgresql")

JSONType = PGJSONB if is_postgres else JSON
UUIDType = PGUUID(as_uuid=True) if is_postgres else String(36)

def PG_UUID_DEFAULT():
    """Postgres'te server-side UUID üret, diğerlerinde None (Python default kullanılır)."""
    return sa_text("gen_random_uuid()") if is_postgres else None

def PG_JSONB_EMPTY():
    """Postgres'te '{}'::jsonb, diğerlerinde '{}' (string) default."""
    return sa_text("'{}'::jsonb") if is_postgres else "{}"


# --- Enums (Python) ---
class ContentLabel(str, Enum):
    alcohol = "alcohol"
    blood = "blood"
    violence = "violence"
    phobic = "phobic"
    obscene = "obscene"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class VideoStatus(str, Enum):
    uploaded = "uploaded"
    analyzed = "analyzed"
    redacted = "redacted"


class RedactMode(str, Enum):
    skip = "skip"
    blur = "blur"
    warn = "warn"


# --- Models ---
class User(Base):
    __tablename__ = "users"

    id = Column(
        UUIDType,
        primary_key=True,
        server_default=PG_UUID_DEFAULT(),
        default=(None if is_postgres else uuid.uuid4),
    )
    # CITEXT yerine portable olması için TEXT + unique
    email = Column(Text, nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    profiles = relationship("PreferenceProfile", back_populates="user", cascade="all, delete-orphan")


class PreferenceProfile(Base):
    __tablename__ = "preference_profiles"

    id = Column(
        UUIDType,
        primary_key=True,
        server_default=PG_UUID_DEFAULT(),
        default=(None if is_postgres else uuid.uuid4),
    )
    user_id = Column(UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False, default="default")

    allow_alcohol  = Column(Boolean, nullable=False, default=False)
    allow_blood    = Column(Boolean, nullable=False, default=False)
    allow_violence = Column(Boolean, nullable=False, default=False)
    allow_phobic   = Column(Boolean, nullable=False, default=False)
    allow_obscene  = Column(Boolean, nullable=False, default=False)

    mode = Column(
        SAEnum(RedactMode, name="redact_mode_enum", native_enum=is_postgres),
        nullable=False, default=RedactMode.blur
    )
    extras = Column(JSONType, nullable=False, server_default=PG_JSONB_EMPTY())

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="profiles")

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_profile_user_name"),
    )


class VideoAsset(Base):
    __tablename__ = "video_assets"

    id = Column(
        UUIDType,
        primary_key=True,
        server_default=PG_UUID_DEFAULT(),
        default=(None if is_postgres else uuid.uuid4),
    )
    owner_user_id = Column(UUIDType, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    title = Column(Text, nullable=False)
    source_url = Column(Text, nullable=True)
    storage_key = Column(Text, nullable=False, unique=True)

    size_bytes = Column(Integer, nullable=True)
    duration_sec = Column(Numeric(10, 3), nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    fps = Column(Numeric(6, 3), nullable=True)
    checksum_sha256 = Column(Text, nullable=True)

    status = Column(
        SAEnum(VideoStatus, name="video_status_enum", native_enum=is_postgres),
        nullable=False, default=VideoStatus.uploaded
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    jobs = relationship("AnalysisJob", back_populates="video", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="ck_video_size"),
        CheckConstraint("duration_sec IS NULL OR duration_sec >= 0", name="ck_video_duration"),
        Index("idx_video_owner", "owner_user_id"),
    )


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id = Column(
        UUIDType,
        primary_key=True,
        server_default=PG_UUID_DEFAULT(),
        default=(None if is_postgres else uuid.uuid4),
    )
    video_id = Column(UUIDType, ForeignKey("video_assets.id", ondelete="CASCADE"), nullable=False)

    status = Column(
        SAEnum(JobStatus, name="job_status_enum", native_enum=is_postgres),
        nullable=False, default=JobStatus.queued
    )
    params = Column(JSONType, nullable=False, server_default=PG_JSONB_EMPTY())
    model_versions = Column(JSONType, nullable=False, server_default=PG_JSONB_EMPTY())

    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    video = relationship("VideoAsset", back_populates="jobs")
    detections = relationship("DetectionEvent", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_job_video", "video_id"),
    )


class DetectionEvent(Base):
    __tablename__ = "detection_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(UUIDType, ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False)

    ts_ms = Column(Integer, nullable=False)
    label = Column(SAEnum(ContentLabel, name="content_label_enum", native_enum=is_postgres), nullable=False)
    score = Column(Float, nullable=False)
    bbox = Column(JSONType, nullable=True)
    track_id = Column(Integer, nullable=True)
    extra = Column(JSONType, nullable=False, server_default=PG_JSONB_EMPTY())
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    job = relationship("AnalysisJob", back_populates="detections")

    __table_args__ = (
        CheckConstraint("ts_ms >= 0", name="ck_det_ts"),
        CheckConstraint("score >= 0 AND score <= 1", name="ck_det_score"),
        Index("idx_det_job_ts", "job_id", "ts_ms"),
        Index("idx_det_label", "label"),
    )


class RedactionPlan(Base):
    __tablename__ = "redaction_plans"

    id = Column(
        UUIDType,
        primary_key=True,
        server_default=PG_UUID_DEFAULT(),
        default=(None if is_postgres else uuid.uuid4),
    )
    video_id = Column(UUIDType, ForeignKey("video_assets.id", ondelete="CASCADE"), nullable=False)
    profile_id = Column(UUIDType, ForeignKey("preference_profiles.id", ondelete="CASCADE"), nullable=False)

    profile_hash = Column(Text, nullable=False)  # user_prefs + model_versions hash
    plan = Column(JSONType, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("video_id", "profile_hash", name="uq_plan_video_hash"),
        Index("idx_plan_video_hash", "video_id", "profile_hash"),
    )