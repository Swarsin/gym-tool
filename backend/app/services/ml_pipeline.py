import traceback
import asyncio
import copy
import os
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import BiomechanicsLog, Workout

# Note: We use absolute imports here since the files are in the same module
from app.services.video_processor import PoseExtractor
from app.services.biomechanics import analyze_set
from app.services.video_timing import active_frame_range, frame_times, sampling_fps, timeline_end
from app.services.coach_agent import CoachAgent
from app.services.storage import is_r2_configured, upload_file_to_r2, delete_r2_file

from typing import Optional, Dict, Any, List, Tuple


def _rebase_metrics_for_active_range(set_metrics, active_range):
    """Align persisted rep/skeleton indices with an auto-trimmed overlay video."""
    if not active_range:
        return

    active_start, active_end = active_range
    frames_3d = set_metrics.get("skeleton_3d_frames") or []
    sliced_3d = frames_3d[active_start:active_end + 1]
    base_time = sliced_3d[0].get("timestamp_s", 0.0) if sliced_3d else 0.0
    for new_idx, frame in enumerate(sliced_3d):
        frame["frame_idx"] = new_idx
        frame["timestamp_s"] = max(
            0.0,
            round(float(frame.get("timestamp_s", base_time)) - float(base_time), 3),
        )
    set_metrics["skeleton_3d_frames"] = sliced_3d

    for rep in set_metrics.get("reps_data") or []:
        rep["start_idx"] = max(0, int(rep.get("start_idx", 0)) - active_start)
        rep["peak_idx"] = max(0, int(rep.get("peak_idx", 0)) - active_start)
        rep["end_idx"] = min(
            active_end - active_start,
            max(0, int(rep.get("end_idx", 0)) - active_start),
        )

async def process_video_task(
    log_id: int,
    video_storage_path: str,
    db: AsyncSession,
    user_height_cm: Optional[float] = None,
    trim_start_s: Optional[float] = None,
    trim_end_s: Optional[float] = None
):
    temporary_paths = set()
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_ANON_KEY")
    try:
        # 1. Update status to 'processing'
        stmt = select(BiomechanicsLog).where(BiomechanicsLog.id == log_id)
        result = await db.execute(stmt)
        log_entry = result.scalar_one_or_none()
        
        if not log_entry:
            await db.close()
            return
            
        log_entry.status = "processing"
        await db.commit()

        # Download video from Storage
        import urllib.request
        import tempfile
        import subprocess

        local_video_path = video_storage_path
        if video_storage_path.startswith("http"):
            print(f"[{log_id}] Starting video download...")
            t0 = time.time()
            temp_dir = tempfile.gettempdir()
            local_video_path = os.path.join(temp_dir, f"temp_video_{log_id}.mp4")
            temporary_paths.add(local_video_path)
            req = urllib.request.Request(
                video_storage_path,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            max_download_bytes = 150 * 1024 * 1024
            def _download_video():
                with urllib.request.urlopen(req, timeout=30) as resp, open(local_video_path, "wb") as out_file:
                    content_length = resp.headers.get("Content-Length")
                    if content_length and int(content_length) > max_download_bytes:
                        raise ValueError("Remote video exceeds the 150 MB processing limit")

                    downloaded = 0
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        downloaded += len(chunk)
                        if downloaded > max_download_bytes:
                            raise ValueError("Remote video exceeds the 150 MB processing limit")
                        out_file.write(chunk)

            await asyncio.to_thread(_download_video)
            t1 = time.time()
            print(f"[{log_id}] Video download took {t1-t0:.2f}s")

        # If user specified client-side trim timestamps, slice before pose extraction
        trim_started = time.perf_counter()
        if (trim_start_s is not None and trim_start_s > 0) or (trim_end_s is not None and trim_end_s > 0):
            try:
                import imageio_ffmpeg
                ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
                trimmed_path = os.path.join(tempfile.gettempdir(), f"client_trimmed_{log_id}.mp4")
                t_start = max(0.0, float(trim_start_s or 0.0))
                t_end = float(trim_end_s) if trim_end_s else None
                t_dur = (t_end - t_start) if (t_end and t_end > t_start) else None

                cmd = [ffmpeg_bin, "-y", "-ss", f"{t_start:.3f}"]
                if t_dur:
                    cmd.extend(["-t", f"{t_dur:.3f}"])
                cmd.extend([
                    "-i", local_video_path,
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart",
                    trimmed_path
                ])
                res = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True)
                if res.returncode == 0 and os.path.exists(trimmed_path) and os.path.getsize(trimmed_path) > 1000:
                    print(f"Applied frame-accurate client trim: {t_start:.2f}s for duration {t_dur if t_dur else 'end'}s -> {trimmed_path}")
                    local_video_path = trimmed_path
                    temporary_paths.add(trimmed_path)
                else:
                    print(f"FFmpeg trim notice: {res.stderr[:200] if res.stderr else 'unknown'}")
            except Exception as trim_err:
                print(f"Warning: Client trim failed ({trim_err}), processing full video.")

        print(f"[{log_id}] Client trim took {time.perf_counter() - trim_started:.2f}s")

        # 2. Extract Landmarks (defaults to model_complexity=1: pose_landmarker_full.task)
        print(f"[{log_id}] Starting landmark extraction...")
        t0 = time.time()
        extractor = PoseExtractor()
        frame_data = await asyncio.to_thread(extractor.extract_from_video, local_video_path)
        t1 = time.time()
        print(f"[{log_id}] Landmark extraction took {t1-t0:.2f}s")
        print(f"[{log_id}] Extraction profile: {extractor.last_profile}")
        actual_fps = sampling_fps(frame_data)

        # Fetch exercise name from workout
        stmt_w = select(Workout).where(Workout.id == log_entry.workout_id)
        res_w = await db.execute(stmt_w)
        workout_entry = res_w.scalar_one_or_none()
        exercise_name = workout_entry.exercise_name if workout_entry else "Lat Pulldown (Lower-Lat Bias)"

        # 3. Analyze Biomechanics with Exercise-Specific Kinematic Driver
        print(f"[{log_id}] Starting biomechanical analysis...")
        t0 = time.time()
        set_metrics = await asyncio.to_thread(
            analyze_set,
            frame_data,
            actual_fps,
            user_height_cm,
            exercise_name,
        )
        t1 = time.time()
        print(f"[{log_id}] Biomechanical analysis took {t1-t0:.2f}s")
        set_metrics["exercise_name"] = exercise_name
        set_metrics["sampling_fps"] = actual_fps
        # Persist profiling alongside existing JSON metrics, for production comparisons.
        set_metrics["extraction_profile"] = extractor.last_profile if isinstance(extractor.last_profile, dict) else {}

        def _sanitize_for_json(val):
            if isinstance(val, dict):
                return {k: _sanitize_for_json(v) for k, v in val.items()}
            elif isinstance(val, (list, tuple)):
                return [_sanitize_for_json(x) for x in val]
            elif hasattr(val, 'item'):  # NumPy scalars (int64, float64, bool_)
                return val.item()
            elif hasattr(val, 'tolist'):  # NumPy ndarrays
                return val.tolist()
            return val

        set_metrics = _sanitize_for_json(set_metrics)

        # 4. Compute set averages and active set range immediately (takes <1ms)
        reps_data = set_metrics.get("reps_data", [])
        avg_eccentric = sum(r.get("eccentric_tempo_s", 0) for r in reps_data) / len(reps_data) if reps_data else 0
        avg_flare = sum(r.get("contraction_elbow_flare_degrees", 0) for r in reps_data) / len(reps_data) if reps_data else 0

        # Automatic Active Set Range Detection (crops out walk-up and walk-back dead time)
        active_range = active_frame_range(frame_data, reps_data)
        if reps_data and len(reps_data) > 0:
            total_extracted = len(frame_data)
            if active_range:
                active_start, active_end = active_range
                times = frame_times(frame_data)
                end_time = times[active_end + 1] if active_end + 1 < len(times) else timeline_end(frame_data, times)
                print(f"Auto-trimming active set window: frames {active_start} -> {active_end} of {total_extracted}")
                
                set_metrics["active_range"] = {
                    "start_frame": active_start,
                    "end_frame": active_end,
                    "original_total_frames": total_extracted,
                    "trimmed_duration_s": round(end_time - times[active_start], 2)
                }

        # 5. Execute Gemini AI Feedback and Video Overlay Rendering CONCURRENTLY
        # Gemini is network I/O; rendering is CPU-bound. Running both together hides LLM latency completely.
        async def _run_gemini_feedback() -> Dict[str, Any]:
            from dotenv import load_dotenv
            from langchain_google_genai import ChatGoogleGenerativeAI
            
            load_dotenv()
            gemini_key = os.getenv("GEMINI_API_KEY", "").strip("\"' \t\r\n")
            gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
            
            if gemini_key:
                try:
                    llm = ChatGoogleGenerativeAI(temperature=0, model=gemini_model, google_api_key=gemini_key)
                    coach = CoachAgent(llm=llm)
                    ai_feedback = await asyncio.to_thread(coach.generate_feedback, set_metrics)
                    return _sanitize_for_json(ai_feedback.model_dump())
                except Exception as gemini_err:
                    print(f"Gemini feedback generation error: {gemini_err}")
            
            coach = CoachAgent(llm=None)
            ai_feedback = await asyncio.to_thread(coach.generate_feedback, set_metrics)
            return _sanitize_for_json(ai_feedback.model_dump())

        async def _run_video_render_and_upload() -> Optional[str]:
            from app.services.video_renderer import render_overlay_video

            overlay_url = None
            try:
                import time as _time
                overlay_filename = f"overlay_{log_id}_{int(_time.time())}.mp4"
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                static_dir = os.path.join(base_dir, "static", "overlays")
                os.makedirs(static_dir, exist_ok=True)
                overlay_path = os.path.join(static_dir, overlay_filename)

                await asyncio.to_thread(
                    render_overlay_video,
                    local_video_path,
                    frame_data,
                    set_metrics,
                    overlay_path,
                    active_range,
                )

                # Determine fallback local URL
                railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
                if railway_domain:
                    overlay_url = f"https://{railway_domain}/static/overlays/{overlay_filename}"
                else:
                    overlay_url = f"http://localhost:8000/static/overlays/{overlay_filename}"

                # Upload to Cloudflare R2 (preferred) or Supabase Storage
                if is_r2_configured():
                    try:
                        storage_path = f"overlays/{overlay_filename}"
                        r2_url = await asyncio.to_thread(upload_file_to_r2, overlay_path, storage_path, "video/mp4")
                        if r2_url:
                            overlay_url = r2_url
                            print(f"Overlay successfully uploaded to Cloudflare R2: {overlay_url}")
                    except Exception as r2_err:
                        print(f"R2 overlay upload warning: {r2_err}")
                elif supabase_url and supabase_key:
                    try:
                        from supabase import create_client
                        storage_path = f"overlays/{overlay_filename}"

                        def _upload_overlay():
                            sb = create_client(supabase_url, supabase_key)
                            sb.storage.from_("workout-videos").upload(
                                storage_path,
                                overlay_path,
                                file_options={"content-type": "video/mp4", "upsert": "true"},
                            )
                            return sb.storage.from_("workout-videos").get_public_url(storage_path)

                        overlay_url = await asyncio.to_thread(_upload_overlay)
                        print(f"Overlay successfully uploaded to Supabase Storage: {overlay_url}")
                    except Exception as sb_err:
                        print(f"Supabase upload skipped/failed ({sb_err}), using static URL: {overlay_url}")

            except Exception as render_err:
                print(f"Warning: Overlay rendering failed (non-fatal): {render_err}")
                import traceback as tb
                tb.print_exc()

            return overlay_url

        # 5. Launch video rendering in background task
        print(f"[{log_id}] Starting Phase 1 commit (metrics only) and concurrent Gemini / Rendering...")
        t0_phase1 = time.time()
        render_task = asyncio.create_task(_run_video_render_and_upload())

        # 6. Generate Gemini AI Feedback concurrently
        gemini_task = asyncio.create_task(_run_gemini_feedback())

        # PHASE 1 COMMIT: Write metrics, reps, and 3D skeleton immediately!
        # The user's screen unlocks right here, showing scorecard & 3D skeleton viewer.
        rebased_metrics = copy.deepcopy(set_metrics)
        _rebase_metrics_for_active_range(rebased_metrics, active_range)

        log_entry.total_reps = set_metrics.get("total_reps", 0)
        log_entry.avg_eccentric_tempo = avg_eccentric
        log_entry.avg_elbow_flare = avg_flare
        log_entry.raw_timeseries_data = rebased_metrics
        # Coach feedback is not ready yet, but set status to unlock frontend
        log_entry.status = "metrics_ready"
        await db.commit()
        t1_phase1 = time.time()
        print(f"[Phase 1] Instant metrics saved for log #{log_id} (status: metrics_ready) - took {t1_phase1-t0_phase1:.2f}s")

        # PHASE 1.5 COMMIT: Wait for Gemini AI Feedback
        try:
            feedback_dict = await gemini_task
            log_entry.coach_feedback = feedback_dict
            await db.commit()
            print(f"[Phase 1.5] AI coaching saved for log #{log_id}")
        except Exception as gemini_task_err:
            print(f"Warning: Gemini task encountered an error: {gemini_task_err}")

        # PHASE 2: Wait for background video rendering & upload to finish
        try:
            overlay_video_url = await render_task
        except Exception as render_task_err:
            print(f"Warning: Render task encountered an error: {render_task_err}")
            overlay_video_url = None

        log_entry.overlay_video_url = overlay_video_url
        log_entry.status = "completed"
        await db.commit()
        print(f"[Phase 2] Annotated video overlay completed & uploaded for log #{log_id} (status: completed)")

        # 7. Prune the raw uploaded phone video to prevent exceeding storage quota
        try:
            if is_r2_configured() and video_storage_path and ("r2.dev" in video_storage_path or "r2.cloudflarestorage.com" in video_storage_path):
                try:
                    await asyncio.to_thread(delete_r2_file, video_storage_path)
                except Exception as r2_prune_err:
                    print(f"Notice: R2 raw video cleanup skipped: {r2_prune_err}")
            elif supabase_url and supabase_key and video_storage_path:
                try:
                    raw_rel_path = None
                    if "/workout-videos/" in video_storage_path:
                        raw_rel_path = video_storage_path.split("/workout-videos/")[-1].split("?")[0]
                    elif video_storage_path.startswith("uploads/"):
                        raw_rel_path = video_storage_path

                    if raw_rel_path and raw_rel_path.startswith("uploads/"):
                        def _delete_raw_upload():
                            try:
                                from supabase import create_client
                                sb = create_client(supabase_url, supabase_key)
                                sb.storage.from_("workout-videos").remove([raw_rel_path])
                            except Exception as sb_e:
                                print(f"Notice: Supabase client remove skipped: {sb_e}")

                        await asyncio.to_thread(_delete_raw_upload)
                        print(f"Pruned raw upload to conserve storage quota: {raw_rel_path}")
                except Exception as prune_err:
                    print(f"Notice: Raw video cleanup skipped: {prune_err}")
        except Exception as cleanup_err:
            print(f"Notice: Video cleanup encountered non-fatal error: {cleanup_err}")

    except Exception as e:
        print(f"Error processing video: {e}")
        print(traceback.format_exc())
        
        stmt = select(BiomechanicsLog).where(BiomechanicsLog.id == log_id)
        result = await db.execute(stmt)
        log_entry = result.scalar_one_or_none()
        if log_entry and log_entry.status not in ("completed", "metrics_ready"):
            log_entry.status = "failed"
            await db.commit()
            
    finally:
        for temp_path in temporary_paths:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
        await db.close()
