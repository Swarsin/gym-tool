import os
import json
import argparse
from video_processor import PoseExtractor
from biomechanics import analyze_set
from coach_agent import CoachAgent

def main():
    parser = argparse.ArgumentParser(description="Form & Biomechanics Analyzer")
    parser.add_argument("--video", type=str, required=True, help="Path to the input video file (e.g., data/raw_video.mp4)")
    parser.add_argument("--fps", type=float, default=30.0, help="Frames per second of the video")
    parser.add_argument("--output", type=str, default="data/output_log.json", help="Path to save the JSON output")
    args = parser.parse_args()

    video_path = args.video
    output_path = args.output
    
    if not os.path.exists(video_path):
        print(f"Error: Video file '{video_path}' not found.")
        return

    print("Step 1: Extracting landmarks using MediaPipe (model_complexity=2)...")
    extractor = PoseExtractor(model_complexity=2)
    frame_data = extractor.extract_from_video(video_path)
    print(f"Extracted data for {len(frame_data)} frames.")

    print("\nStep 2: Performing biomechanical analysis...")
    set_metrics = analyze_set(frame_data, fps=args.fps)
    print(f"Found {set_metrics['total_reps']} reps.")
    for rep in set_metrics['reps_data']:
        print(f"  Rep {rep['rep_number']}: "
              f"Flare={rep['peak_concentric_elbow_flare_degrees']}°, "
              f"Ecc={rep['eccentric_tempo_s']}s, "
              f"Con={rep['concentric_tempo_s']}s")

    print("\nStep 3: Generating LLM Coach Feedback...")
    # NOTE: To run the LLM, you need to import your model and pass it to CoachAgent.
    # Example using OpenAI:
    # from langchain_openai import ChatOpenAI
    # llm = ChatOpenAI(model="gpt-4-turbo", temperature=0)
    # agent = CoachAgent(llm)
    # feedback = agent.generate_feedback(set_metrics)
    # feedback_dict = feedback.model_dump()
    
    # Placeholder so the script can run purely locally without API keys initially:
    feedback_dict = {
        "overall_score": 0,
        "primary_flaw": "LLM Integration not active",
        "actionable_cues": ["Instantiate LLM in main.py", "Pass LLM to CoachAgent", "Provide API keys"],
        "hypertrophy_analysis": "To see hypertrophy analysis, please wire up the LangChain chat model in main.py."
    }
    
    print("\n--- Biomechanics Feedback ---")
    print(json.dumps(feedback_dict, indent=2))

    # Save to logs
    log_data = {
        "metrics": set_metrics,
        "feedback": feedback_dict
    }
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(log_data, f, indent=4)
        
    print(f"\nAnalysis complete. Results saved to {output_path}")

if __name__ == "__main__":
    main()
