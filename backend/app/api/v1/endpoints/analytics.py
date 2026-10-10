import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Workout, BiomechanicsLog, User
from app.schemas import AnalyticsTrendsResponse, TrendDataPoint, OverloadDelta
from app.core.auth import get_current_user

router = APIRouter()

@router.get("/trends", response_model=AnalyticsTrendsResponse)
async def get_workout_trends(
    exercise: Optional[str] = Query("all", description="Filter by exercise name or 'all'"),
    time_range: Optional[str] = Query("all", description="Time range: 7d, 30d, 90d, all"),
    user_id: Optional[uuid.UUID] = Query(None, description="Filter by user UUID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Computes longitudinal Velocity-Based Training (VBT) and biomechanical trends
    across all historical workouts for progressive overload tracking.
    """
    if user_id and user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view another user's trends.",
        )
    effective_user_id = current_user.id

    # 1. Base Query
    conditions = [
        BiomechanicsLog.status == "completed",
        Workout.user_id == effective_user_id
    ]

    if exercise and exercise.lower() != "all":
        conditions.append(Workout.exercise_name == exercise)

    # Time range filter
    now = datetime.utcnow()
    if time_range == "7d":
        conditions.append(Workout.created_at >= now - timedelta(days=7))
    elif time_range == "30d":
        conditions.append(Workout.created_at >= now - timedelta(days=30))
    elif time_range == "90d":
        conditions.append(Workout.created_at >= now - timedelta(days=90))

    stmt = (
        select(Workout, BiomechanicsLog)
        .join(BiomechanicsLog, Workout.id == BiomechanicsLog.workout_id)
        .where(and_(*conditions))
        .order_by(Workout.created_at.asc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    # 2. Extract Data Points
    data_points: List[TrendDataPoint] = []
    
    for workout, log in rows:
        ts_data = log.raw_timeseries_data or {}
        vbt = ts_data.get("vbt_summary") or {}
        reps_data = ts_data.get("reps_data") or []

        # Mean velocity
        mean_vel = vbt.get("avg_concentric_velocity_mps")
        if mean_vel is None or mean_vel <= 0:
            if reps_data:
                valid_speeds = [r.get("mean_velocity_mps", 0) for r in reps_data if r.get("mean_velocity_mps")]
                mean_vel = sum(valid_speeds) / len(valid_speeds) if valid_speeds else 0.0
            else:
                mean_vel = 0.0

        # Peak velocity
        if reps_data:
            measured_peaks = [r.get("peak_velocity_mps", 0) for r in reps_data if r.get("peak_velocity_mps")]
            peak_vel = max(measured_peaks) if measured_peaks else mean_vel
        else:
            peak_vel = mean_vel

        # Velocity loss %
        vel_loss = vbt.get("velocity_loss_pct")
        if vel_loss is None and reps_data and len(reps_data) >= 2:
            speeds = [r.get("mean_velocity_mps", 0) for r in reps_data if r.get("mean_velocity_mps")]
            if len(speeds) >= 2 and max(speeds) > 0:
                vel_loss = max(0.0, ((max(speeds) - speeds[-1]) / max(speeds)) * 100.0)

        # ROM consistency
        if reps_data:
            rom_pcts = [r.get("concentric_rom_percent", r.get("concentric_rom_pct", 0.0)) for r in reps_data]
            avg_rom = sum(rom_pcts) / len(rom_pcts) if rom_pcts else 0.0
        else:
            avg_rom = 0.0

        rpe = vbt.get("estimated_rpe")

        data_points.append(
            TrendDataPoint(
                log_id=log.id,
                workout_id=workout.id,
                date=workout.created_at.strftime("%b %d, %H:%M"),
                timestamp=workout.created_at,
                exercise_name=workout.exercise_name or "Pull-Up / Chin-Up",
                total_reps=log.total_reps or len(reps_data),
                mean_concentric_velocity=round(float(mean_vel), 2),
                peak_concentric_velocity=round(float(peak_vel), 2),
                velocity_loss_pct=round(float(vel_loss), 1) if vel_loss is not None else None,
                avg_eccentric_tempo=round(float(log.avg_eccentric_tempo or 0.0), 1),
                avg_elbow_flare=round(float(log.avg_elbow_flare or 0.0), 1),
                rom_consistency_pct=round(float(avg_rom), 1),
                estimated_rpe=round(float(rpe), 1) if rpe else None,
                overlay_video_url=log.overlay_video_url
            )
        )

    # 3. Calculate Progressive Overload Metrics
    n = len(data_points)
    total_volume = sum(dp.total_reps for dp in data_points)

    if n == 0:
        overload_delta = OverloadDelta(
            velocity_delta_pct=0.0,
            fastest_rep_delta_pct=0.0,
            tempo_stability_pct=100.0,
            rom_standardization_score=100.0,
            total_volume_reps=0,
            sessions_analyzed=0,
            adaptation_status="No sessions recorded"
        )
        insight = "Start logging sets to track your progressive overload velocity trends."
    elif n < 3:
        avg_v = sum(dp.mean_concentric_velocity for dp in data_points) / n
        avg_rom_score = sum(dp.rom_consistency_pct for dp in data_points) / n
        overload_delta = OverloadDelta(
            velocity_delta_pct=0.0,
            fastest_rep_delta_pct=0.0,
            tempo_stability_pct=95.0,
            rom_standardization_score=round(avg_rom_score, 1),
            total_volume_reps=total_volume,
            sessions_analyzed=n,
            adaptation_status="Baseline Establishing"
        )
        insight = f"Baseline established across {n} session{'s' if n > 1 else ''} with an average concentric speed of {avg_v:.2f} m/s."
    else:
        # Compare first 33% vs last 33% (or first 2 vs last 2)
        sample_size = max(1, n // 3)
        baseline_slice = data_points[:sample_size]
        recent_slice = data_points[-sample_size:]

        base_v = sum(dp.mean_concentric_velocity for dp in baseline_slice) / len(baseline_slice)
        recent_v = sum(dp.mean_concentric_velocity for dp in recent_slice) / len(recent_slice)
        
        base_peak = sum(dp.peak_concentric_velocity for dp in baseline_slice) / len(baseline_slice)
        recent_peak = sum(dp.peak_concentric_velocity for dp in recent_slice) / len(recent_slice)

        v_delta = ((recent_v - base_v) / base_v) * 100.0 if base_v > 0 else 0.0
        peak_delta = ((recent_peak - base_peak) / base_peak) * 100.0 if base_peak > 0 else 0.0

        # Tempo consistency
        tempos = [dp.avg_eccentric_tempo for dp in data_points]
        mean_tempo = sum(tempos) / len(tempos)
        tempo_var = sum((t - mean_tempo) ** 2 for t in tempos) / len(tempos)
        tempo_std = tempo_var ** 0.5
        tempo_stability = max(50.0, min(100.0, 100.0 - (tempo_std * 25.0)))

        # Average ROM score
        avg_rom_score = sum(dp.rom_consistency_pct for dp in data_points) / len(data_points)

        # Status determination
        if v_delta >= 5.0:
            status = f"Neuromuscular Force Acceleration (+{v_delta:.1f}%)"
            insight = f"Progressive overload confirmed! Your mean concentric drive speed increased by +{v_delta:.1f}% across your last {n} logged workouts while maintaining a steady {mean_tempo:.1f}s eccentric tempo."
        elif v_delta <= -5.0:
            status = f"Load Progression / High Density ({v_delta:.1f}%)"
            insight = f"Mean velocity shifted by {v_delta:.1f}% across {n} workouts, indicating heavier working loads or accumulating set fatigue. Ensure eccentric control remains around {mean_tempo:.1f}s."
        else:
            status = "Consistent Strength & Motor Pattern"
            insight = f"High motor pattern consistency: Velocity remained locked at ~{recent_v:.2f} m/s across {n} sessions with {avg_rom_score:.1f}% ROM standardization."

        overload_delta = OverloadDelta(
            velocity_delta_pct=round(v_delta, 1),
            fastest_rep_delta_pct=round(peak_delta, 1),
            tempo_stability_pct=round(tempo_stability, 1),
            rom_standardization_score=round(avg_rom_score, 1),
            total_volume_reps=total_volume,
            sessions_analyzed=n,
            adaptation_status=status
        )

    return AnalyticsTrendsResponse(
        time_range=time_range or "all",
        exercise_filter=exercise or "all",
        data_points=data_points,
        overload_delta=overload_delta,
        macro_ai_insight=insight
    )
