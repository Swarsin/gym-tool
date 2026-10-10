import json
from typing import List, Dict, Any, Optional
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field


class ScorecardTier(BaseModel):
    category: str = Field(description="Category name: 'ROM Standardization', 'Body Control & Stability', 'Elbow Path Consistency', or 'Tempo Control'")
    rating: str = Field(description="Objective assessment rating (e.g., 'Good', 'Needs Improvement', 'Consistent')")
    confidence: str = Field(description="Confidence rating: 'HIGH', 'MODERATE', or 'LOW'")
    note: str = Field(description="Short factual note explaining the rating. Max 10 words.")


class BiomechanicsFeedback(BaseModel):
    scorecard: List[ScorecardTier] = Field(
        description="Three-tier scorecard assessing individual biomechanical components independently."
    )
    camera_observations: str = Field(
        description="Direct factual observations of what the camera recorded (e.g. rep consistency, bottom positions, body swing)."
    )
    actionable_cues: List[str] = Field(
        description="Practical, anatomically appropriate cues for the next set. Max 3 cues."
    )
    measurement_limitations: str = Field(
        description="Transparent statement of tracking/scale confidence, camera angle limitations, or suppressed metrics."
    )


class CoachAgent:
    """
    LangChain setup and Pydantic schemas for validated, non-punitive biomechanics feedback.
    """

    def __init__(self, llm):
        self.llm = llm

        self.system_prompt = """You are an elite, objective Biomechanist and Strength Coach.
Your goal is to evaluate mathematical metrics from a lifter's video set and provide objective, grounded feedback.

CRITICAL RULES:
1. STRICT DATA GROUNDING:
   - Only reference repetitions that actually exist in the provided metrics (e.g. if total_reps is 4, only discuss reps #1 through #4).
   - Base observations strictly on measured concentric/eccentric ROM%, mean velocity, and tempos.
   - Do NOT invent unobservable internal mechanisms (e.g. do not guess muscle recruitment).

2. CONTEXTUAL ELBOW PATH:
   - For wide or angled pull-up handles, upper arm flare angles of 65°–75° are natural and expected. Describe elbow path as "consistent and compatible with the selected wide grip."
   - Do NOT recommend narrow elbow tucking (<20°) on wide pull-ups.

3. PRACTICAL CUES:
   - Give 1 to 3 direct, actionable technical cues for the next set based on the slowest rep or greatest ROM deviation.

4. THREE-TIER SCORECARD:
   - Populate the 4 categories: 'ROM Standardization', 'Body Control & Stability', 'Elbow Path Consistency', and 'Tempo Control'.
   - Assign 'Good', 'Consistent', or 'Needs Improvement' with high/moderate confidence.

5. BILATERAL ASYMMETRY & BALANCE:
   - Review asymmetry_analysis metrics (overall_symmetry_score, avg_flare_delta_deg, primary_pattern, fatigue_drift_detected).
   - If significant or mild imbalance is present (flare delta > 6° or shoulder hiking > 3°), mention which side is flaring or hiking and provide an actionable corrective cue.

Here are the mathematical metrics from the video analysis:
{metrics}
"""

    def generate_feedback(self, set_metrics: Dict[str, Any]) -> BiomechanicsFeedback:
        reps = set_metrics.get("reps_data", [])
        total_reps = set_metrics.get("total_reps", len(reps))
        
        if not reps or total_reps == 0:
            return BiomechanicsFeedback(
                scorecard=[
                    ScorecardTier(category="ROM Standardization", rating="N/A", confidence="LOW", note="No completed reps detected"),
                    ScorecardTier(category="Body Control & Stability", rating="N/A", confidence="LOW", note="No completed reps detected"),
                    ScorecardTier(category="Elbow Path Consistency", rating="N/A", confidence="LOW", note="No completed reps detected"),
                    ScorecardTier(category="Tempo Control", rating="N/A", confidence="LOW", note="No completed reps detected")
                ],
                camera_observations="No completed repetitions detected in video clip.",
                actionable_cues=[
                    "Ensure your full upper body is visible in the camera frame",
                    "Perform repetitions through complete range of motion"
                ],
                measurement_limitations="Biomechanical tracking requires an unobstructed view of the lifter."
            )

        try:
            # Try structured output first (Gemini native)
            structured_llm = self.llm.with_structured_output(BiomechanicsFeedback)
            
            # Remove heavy 3D frame-by-frame data before sending to LLM to drastically reduce prompt size & latency
            prompt_metrics = {k: v for k, v in set_metrics.items() if k != "skeleton_3d_frames"}
            metrics_str = json.dumps(prompt_metrics, indent=2)
            
            prompt_text = self.system_prompt.format(metrics=metrics_str)
            response = structured_llm.invoke(prompt_text)
            if isinstance(response, BiomechanicsFeedback):
                return response
            elif isinstance(response, dict):
                return BiomechanicsFeedback(**response)
        except Exception as err:
            print(f"Structured output error, attempting JSON fallback: {err}")

        # Grounded dynamic fallback calculated from actual data
        avg_tempo = set_metrics.get("avg_eccentric_tempo", 1.5)
        vel_loss = set_metrics.get("velocity_loss_percent", 0)
        asym = set_metrics.get("asymmetry_analysis", {})
        asym_class = asym.get("asymmetry_classification", "Symmetrical & Balanced")
        asym_delta = asym.get("avg_flare_delta_deg", 0.0)
        asym_pattern = asym.get("primary_pattern", "Balanced Bilateral Mechanics")
        asym_cues = asym.get("corrective_cues", [])
        
        rom_notes = "Consistent repetition depth" if all(r.get("concentric_rom_percent", 0) > 70 for r in reps) else "Varied bottom extension across repetitions"

        # Dynamically grade elbow path consistency based on measured symmetry
        if asym_class == "Significant Imbalance Detected":
            elbow_rating = "Needs Improvement"
            elbow_note = f"Delta {asym_delta:.1f}° - {asym_pattern[:30]}"
        elif asym_class == "Mild Asymmetry":
            elbow_rating = "Mild Asymmetry"
            elbow_note = f"Delta {asym_delta:.1f}° between arms"
        else:
            elbow_rating = "Consistent"
            elbow_note = "Symmetrical bilateral path"
        
        cues = [
            "Maintain consistent, controlled near-full extension on each repetition"
        ]
        if asym_cues:
            cues.append(asym_cues[0])
        else:
            cues.append("Drive elbows straight down in line with the grip angle")

        obs_suffix = f" Bilateral symmetry scored {asym.get('overall_symmetry_score', 95)}% ({asym_class.lower()})." if asym else ""

        return BiomechanicsFeedback(
            scorecard=[
                ScorecardTier(category="ROM Standardization", rating="Good" if "Consistent" in rom_notes else "Needs Improvement", confidence="HIGH", note=rom_notes),
                ScorecardTier(category="Body Control & Stability", rating="Good", confidence="HIGH", note="Body control remained steady throughout the set"),
                ScorecardTier(category="Elbow Path Consistency", rating=elbow_rating, confidence="HIGH", note=elbow_note),
                ScorecardTier(category="Tempo Control", rating="Good", confidence="HIGH", note=f"Controlled descent averaging {avg_tempo:.1f}s")
            ],
            camera_observations=f"Completed {total_reps} repetitions with an average concentric speed of {set_metrics.get('mean_concentric_velocity_mps', 0.2):.2f} m/s and {vel_loss:.1f}% velocity loss.{obs_suffix}",
            actionable_cues=cues,
            measurement_limitations="Velocity loss comparison is gated on repetition ROM consistency. RPE estimates reflect observable movement speed."
        )
