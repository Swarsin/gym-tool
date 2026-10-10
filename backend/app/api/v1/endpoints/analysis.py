import uuid
import os
from typing import List, Optional
from datetime import datetime
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db, AsyncSessionLocal
from app.models import BiomechanicsLog, Workout, User
from app.schemas import (
    AnalyzeRequest,
    BiomechanicsLogResponse,
    WorkoutHistorySummary,
    DashboardStats
)
from app.core.auth import get_current_user
from app.services.ml_pipeline import process_video_task

from pydantic import BaseModel

router = APIRouter()

ALLOWED_VIDEO_CONTENT_TYPES = {"video/mp4", "video/quicktime", "video/webm"}


class UploadUrlRequest(BaseModel):
    filename: str
    content_type: Optional[str] = "video/mp4"


@router.post("/storage/upload-url")
async def get_upload_url(
    request: UploadUrlRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Generates a secure presigned upload URL directly to Cloudflare R2 object storage.
    Requires strict authentication and validated video MIME type.
    """
    if request.content_type not in ALLOWED_VIDEO_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported video type '{request.content_type}'. Allowed types: {', '.join(sorted(ALLOWED_VIDEO_CONTENT_TYPES))}"
        )

    try:
        from app.services.storage import is_r2_configured, generate_presigned_upload_url
        if is_r2_configured():
            presigned_data = generate_presigned_upload_url(
                original_filename=request.filename,
                content_type=request.content_type or "video/mp4"
            )
            return {
                "provider": "r2",
                "upload_url": presigned_data["upload_url"],
                "public_url": presigned_data["public_url"],
                "storage_key": presigned_data["storage_key"],
            }
        else:
            return {
                "provider": "supabase",
                "upload_url": None,
                "public_url": None,
                "storage_key": None
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze", status_code=status.HTTP_202_ACCEPTED)
async def analyze_video(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    source_url = urlparse(request.video_storage_path)
    if source_url.scheme not in {"http", "https"} or not source_url.hostname:
        raise HTTPException(status_code=422, detail="video_storage_path must be an HTTP(S) storage URL.")

    # Strictly validate storage host against configured environment domains (prevents arbitrary SSRF)
    configured_storage_host = urlparse(os.getenv("SUPABASE_URL", "")).hostname
    r2_public_host = urlparse(os.getenv("R2_PUBLIC_URL", "")).hostname
    allowed_hosts = {h.lower() for h in [configured_storage_host, r2_public_host] if h}

    if not source_url.hostname or source_url.hostname.lower() not in allowed_hosts:
        raise HTTPException(
            status_code=422,
            detail="Video URL must come from an approved storage provider."
        )

    if request.trim_start_s is not None and request.trim_start_s < 0:
        raise HTTPException(status_code=422, detail="trim_start_s must be non-negative.")
    if request.trim_end_s is not None and request.trim_end_s <= 0:
        raise HTTPException(status_code=422, detail="trim_end_s must be greater than zero.")
    if (
        request.trim_start_s is not None
        and request.trim_end_s is not None
        and request.trim_end_s - request.trim_start_s < 0.5
    ):
        raise HTTPException(status_code=422, detail="Trim range must be at least 0.5 seconds.")

    # Target user UUID strictly belongs to authenticated user
    target_user_id = current_user.id

    # Create new workout entry
    workout = Workout(
        user_id=target_user_id,
        exercise_name=request.exercise_name or "Lat Pulldown (Lower-Lat Bias)",
        video_storage_path=request.video_storage_path
    )
    db.add(workout)
    await db.commit()
    await db.refresh(workout)

    # Create pending biomechanics log
    log_entry = BiomechanicsLog(
        workout_id=workout.id,
        status="pending"
    )
    db.add(log_entry)
    await db.commit()
    await db.refresh(log_entry)

    # Spawn background task with its own dedicated DB session
    bg_db = AsyncSessionLocal()
    background_tasks.add_task(
        process_video_task,
        log_entry.id,
        request.video_storage_path,
        bg_db,
        request.user_height_cm,
        request.trim_start_s,
        request.trim_end_s
    )

    return {
        "message": "Analysis started in background.",
        "log_id": log_entry.id,
        "workout_id": workout.id,
        "user_id": str(target_user_id)
    }


@router.get("/results/{log_id}", response_model=BiomechanicsLogResponse)
async def get_results(
    log_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(BiomechanicsLog, Workout)
        .outerjoin(Workout, BiomechanicsLog.workout_id == Workout.id)
        .where(BiomechanicsLog.id == log_id)
    )
    result = await db.execute(stmt)
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Biomechanics log with ID {log_id} not found."
        )

    log_entry, workout = row
    if workout and workout.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this result.",
        )

    created_at_dt = workout.created_at if (workout and workout.created_at) else datetime.utcnow()
    exercise_name = workout.exercise_name if workout else "Lat Pulldown"

    return BiomechanicsLogResponse(
        id=log_entry.id,
        workout_id=log_entry.workout_id,
        exercise_name=exercise_name,
        created_at=created_at_dt,
        status=log_entry.status,
        total_reps=log_entry.total_reps or 0,
        avg_eccentric_tempo=log_entry.avg_eccentric_tempo,
        avg_elbow_flare=log_entry.avg_elbow_flare,
        raw_timeseries_data=log_entry.raw_timeseries_data,
        coach_feedback=log_entry.coach_feedback,
        overlay_video_url=log_entry.overlay_video_url
    )


@router.get("/history", response_model=List[WorkoutHistorySummary])
@router.get("/history/{user_id}", response_model=List[WorkoutHistorySummary])
async def get_workout_history(
    user_id: Optional[uuid.UUID] = None,
    exercise: Optional[str] = Query(None, description="Filter by exercise name"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if user_id and user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view another user's workout history.",
        )

    stmt = (
        select(Workout, BiomechanicsLog)
        .join(BiomechanicsLog, Workout.id == BiomechanicsLog.workout_id)
        .where(Workout.user_id == current_user.id)
        .order_by(Workout.created_at.desc())
    )

    if exercise and exercise != "all":
        stmt = stmt.where(Workout.exercise_name.ilike(f"%{exercise}%"))

    result = await db.execute(stmt)
    rows = result.all()

    history: List[WorkoutHistorySummary] = []
    for workout, log in rows:
        feedback = log.coach_feedback or {}
        history.append(WorkoutHistorySummary(
            workout_id=workout.id,
            log_id=log.id,
            exercise_name=workout.exercise_name,
            created_at=workout.created_at,
            status=log.status,
            total_reps=log.total_reps or 0,
            avg_eccentric_tempo=log.avg_eccentric_tempo or 0.0,
            avg_elbow_flare=log.avg_elbow_flare or 0.0,
            overall_score=feedback.get("overall_score"),
            primary_flaw=feedback.get("primary_flaw"),
            overlay_video_url=log.overlay_video_url
        ))

    return history


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    user_id: Optional[uuid.UUID] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if user_id and user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view another user's statistics.",
        )

    stmt = (
        select(Workout, BiomechanicsLog)
        .join(BiomechanicsLog, Workout.id == BiomechanicsLog.workout_id)
        .where(Workout.user_id == current_user.id)
    )

    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        return DashboardStats(
            total_workouts=0,
            total_reps=0,
            avg_eccentric_tempo=0.0,
            avg_elbow_flare=0.0,
            avg_score=None,
            completed_count=0
        )

    total_workouts = len(rows)
    completed_logs = [log for _, log in rows if log.status == "completed"]
    total_reps = sum(log.total_reps or 0 for log in completed_logs)
    
    tempos = [log.avg_eccentric_tempo for log in completed_logs if log.avg_eccentric_tempo is not None and log.avg_eccentric_tempo > 0]
    flares = [log.avg_elbow_flare for log in completed_logs if log.avg_elbow_flare is not None and log.avg_elbow_flare > 0]
    
    scores = []
    for log in completed_logs:
        if log.coach_feedback and isinstance(log.coach_feedback, dict):
            score = log.coach_feedback.get("overall_score")
            if score is not None:
                scores.append(float(score))

    avg_tempo = round(sum(tempos) / len(tempos), 2) if tempos else 0.0
    avg_flare = round(sum(flares) / len(flares), 1) if flares else 0.0
    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    return DashboardStats(
        total_workouts=total_workouts,
        total_reps=total_reps,
        avg_eccentric_tempo=avg_tempo,
        avg_elbow_flare=avg_flare,
        avg_score=avg_score,
        completed_count=len(completed_logs)
    )


@router.delete("/workout/{workout_id}", status_code=status.HTTP_200_OK)
async def delete_workout(
    workout_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Workout).where(Workout.id == workout_id)
    res = await db.execute(stmt)
    workout = res.scalar_one_or_none()

    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workout {workout_id} not found"
        )

    if workout.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this workout."
        )

    await db.delete(workout)
    await db.commit()

    return {"message": f"Workout {workout_id} deleted successfully."}
