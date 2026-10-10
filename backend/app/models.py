import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    workouts = relationship("Workout", back_populates="user", cascade="all, delete-orphan")


class Workout(Base):
    __tablename__ = "workouts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    exercise_name = Column(String, nullable=False)
    video_storage_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    user = relationship("User", back_populates="workouts")
    biomechanics_log = relationship("BiomechanicsLog", back_populates="workout", uselist=False, cascade="all, delete-orphan")


class BiomechanicsLog(Base):
    __tablename__ = "biomechanics_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workout_id = Column(Integer, ForeignKey("workouts.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    
    total_reps = Column(Integer, default=0)
    avg_eccentric_tempo = Column(Float, nullable=True)
    avg_elbow_flare = Column(Float, nullable=True)
    
    raw_timeseries_data = Column(JSONB, nullable=True)
    coach_feedback = Column(JSONB, nullable=True)
    overlay_video_url = Column(String, nullable=True)
    
    status = Column(String, default="pending", index=True) # pending, processing, completed, failed
    
    # Relationships
    workout = relationship("Workout", back_populates="biomechanics_log")
