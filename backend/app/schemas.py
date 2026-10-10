import uuid
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

class AnalyzeRequest(BaseModel):
    user_id: Optional[uuid.UUID] = None
    workout_id: Optional[int] = None
    video_storage_path: str
    exercise_name: Optional[str] = "Lat Pulldown (Lower-Lat Bias)"
    user_height_cm: Optional[float] = None
    trim_start_s: Optional[float] = None
    trim_end_s: Optional[float] = None

class BiomechanicsLogResponse(BaseModel):
    id: int
    workout_id: int
    exercise_name: Optional[str] = None
    created_at: Optional[datetime] = None
    status: str
    total_reps: Optional[int] = 0
    avg_eccentric_tempo: Optional[float] = None
    avg_elbow_flare: Optional[float] = None
    raw_timeseries_data: Optional[Dict[str, Any]] = None
    coach_feedback: Optional[Dict[str, Any]] = None
    overlay_video_url: Optional[str] = None

    class Config:
        from_attributes = True

class WorkoutHistorySummary(BaseModel):
    log_id: int
    workout_id: int
    exercise_name: str
    created_at: datetime
    status: str = "completed"
    total_reps: Optional[int] = 0
    avg_eccentric_tempo: Optional[float] = 0.0
    avg_elbow_flare: Optional[float] = 0.0
    overall_score: Optional[int] = None
    primary_flaw: Optional[str] = None
    overlay_video_url: Optional[str] = None

    class Config:
        from_attributes = True

class DashboardStats(BaseModel):
    total_workouts: int
    total_reps: int
    avg_eccentric_tempo: float
    avg_elbow_flare: float
    avg_score: Optional[float] = None
    completed_count: int

class TrendDataPoint(BaseModel):
    log_id: int
    workout_id: int
    date: str
    timestamp: datetime
    exercise_name: str
    total_reps: int
    mean_concentric_velocity: float
    peak_concentric_velocity: float
    velocity_loss_pct: Optional[float] = None
    avg_eccentric_tempo: float
    avg_elbow_flare: float
    rom_consistency_pct: float
    estimated_rpe: Optional[float] = None
    overlay_video_url: Optional[str] = None

class OverloadDelta(BaseModel):
    velocity_delta_pct: float
    fastest_rep_delta_pct: float
    tempo_stability_pct: float
    rom_standardization_score: float
    total_volume_reps: int
    sessions_analyzed: int
    adaptation_status: str

class AnalyticsTrendsResponse(BaseModel):
    time_range: str
    exercise_filter: str
    data_points: List[TrendDataPoint]
    overload_delta: OverloadDelta
    macro_ai_insight: str

