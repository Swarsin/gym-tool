"""
Lightweight exercise recognition using a handful of sampled frames and Gemini.

Catches clips whose motion passes the rule-based gates but is clearly a different
exercise (curls, presses, squats, a different pull, etc.). Always fails open: any
error, timeout, missing key or low-confidence answer returns None, and the pipeline
continues with the rule-based gates only.
"""
import base64
import os
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

SUPPORTED_EXERCISES = [
    "Lat Pulldown",
    "Pull-Up / Chin-Up",
    "Barbell Row",
    "Seated Cable Row",
    "Single-Arm Dumbbell Row",
]

# Confidence needed before flagging a mismatch. Higher for confusing two supported
# exercises, since a wrong flag blocks a genuine set.
MIN_CONFIDENCE_OTHER = 0.70
MIN_CONFIDENCE_DIFFERENT_SUPPORTED = 0.85
NUM_FRAMES = 4
MAX_FRAME_SIDE = 512


class ExerciseRecognition(BaseModel):
    exercise: Literal[
        "Lat Pulldown",
        "Pull-Up / Chin-Up",
        "Barbell Row",
        "Seated Cable Row",
        "Single-Arm Dumbbell Row",
        "other_exercise",
        "no_exercise",
    ] = Field(description="The exercise being performed, or other_exercise / no_exercise.")
    other_exercise_name: Optional[str] = Field(
        default=None, description="Short common name if exercise is other_exercise (e.g. 'Barbell Squat')."
    )
    confidence: float = Field(description="Confidence from 0.0 to 1.0.")


_PROMPT = (
    "These frames are sampled in order from one gym video. Identify the exercise being performed. "
    f"Supported exercises: {', '.join(SUPPORTED_EXERCISES)}. "
    "If it is a different exercise answer other_exercise and give its name. "
    "If nobody is exercising (no person, walking, talking, resting) answer no_exercise. "
    "Be strict about equipment and body position: a pull-up hangs from a fixed bar, "
    "a lat pulldown is seated at a cable machine pulling a bar down, rows pull horizontally."
)


def _canonical(exercise_name: str) -> str:
    ex = (exercise_name or "").lower()
    if "pulldown" in ex:
        return "Lat Pulldown"
    if "pull-up" in ex or "chin" in ex:
        return "Pull-Up / Chin-Up"
    if "barbell row" in ex:
        return "Barbell Row"
    if "cable row" in ex:
        return "Seated Cable Row"
    if "dumbbell" in ex:
        return "Single-Arm Dumbbell Row"
    return exercise_name


def sample_frames_jpeg(video_path: str, num_frames: int = NUM_FRAMES) -> List[bytes]:
    import cv2

    cap = cv2.VideoCapture(video_path)
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total <= 0:
            return []
        # Skip the first/last 10% where people are usually walking up or away.
        positions = [int(total * (0.1 + 0.8 * (i + 0.5) / num_frames)) for i in range(num_frames)]
        frames = []
        for pos in positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            h, w = frame.shape[:2]
            scale = MAX_FRAME_SIDE / max(h, w)
            if scale < 1.0:
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ok:
                frames.append(buf.tobytes())
        return frames
    finally:
        cap.release()


def recognize_exercise(video_path: str, selected_exercise: str) -> Optional[Dict[str, Any]]:
    """
    Returns None when the clip is acceptable or the check is inconclusive.
    Returns a dict {detected_exercise, confidence, raw} when the clip confidently
    does not match the selected exercise.
    """
    if os.getenv("EXERCISE_RECOGNITION", "on").strip().lower() in {"off", "0", "false"}:
        return None
    api_key = os.getenv("GEMINI_API_KEY", "").strip("\"' \t\r\n")
    if not api_key:
        return None

    try:
        from langchain_core.messages import HumanMessage
        from langchain_google_genai import ChatGoogleGenerativeAI

        frames = sample_frames_jpeg(video_path)
        if len(frames) < 2:
            return None

        model = os.getenv("GEMINI_RECOGNITION_MODEL") or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        llm = ChatGoogleGenerativeAI(temperature=0, model=model, google_api_key=api_key, timeout=20)
        content: List[Dict[str, Any]] = [{"type": "text", "text": _PROMPT}]
        for jpg in frames:
            content.append({
                "type": "image_url",
                "image_url": "data:image/jpeg;base64," + base64.b64encode(jpg).decode("ascii"),
            })
        result = llm.with_structured_output(ExerciseRecognition).invoke([HumanMessage(content=content)])
        if isinstance(result, dict):
            result = ExerciseRecognition(**result)
        if not isinstance(result, ExerciseRecognition):
            return None
    except Exception as err:  # fail open
        print(f"Exercise recognition skipped: {err}")
        return None

    selected = _canonical(selected_exercise)
    raw = result.model_dump()
    print(f"Exercise recognition: selected={selected} -> {raw}")

    if result.exercise == selected:
        return None
    if result.exercise in ("other_exercise", "no_exercise"):
        if result.confidence < MIN_CONFIDENCE_OTHER:
            return None
        detected = None
        if result.exercise == "other_exercise" and result.other_exercise_name:
            detected = result.other_exercise_name.strip()[:60]
        elif result.exercise == "no_exercise":
            detected = "no exercise"
        return {"detected_exercise": detected, "confidence": result.confidence, "raw": raw}
    # A different supported exercise.
    if result.confidence < MIN_CONFIDENCE_DIFFERENT_SUPPORTED:
        return None
    return {"detected_exercise": result.exercise, "confidence": result.confidence, "raw": raw}
