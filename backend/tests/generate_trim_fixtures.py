"""Generate small, reproducible browser media fixtures (no remote services)."""
from pathlib import Path
import subprocess
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[2]
DESTINATION = ROOT / "frontend" / "tests" / "fixtures"


def main():
    if not DESTINATION.is_dir():
        raise FileNotFoundError(DESTINATION)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    common = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
              "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=30:duration=6",
              "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=6"]
    h264 = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac"]
    def run(arguments):
        subprocess.run(arguments, check=True)
    run(common + h264 + ["-movflags", "+faststart", str(DESTINATION / "source.mp4")])
    run(common + ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-c:a", "libopus",
                  str(DESTINATION / "source.webm")])
    run(common + h264 + ["-vf", "select='not(mod(n,2)) + gte(t,3)'", "-fps_mode", "vfr",
                        str(DESTINATION / "variable.mp4")])
    run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-display_rotation:v:0", "90",
         "-i", str(DESTINATION / "source.mp4"), "-c", "copy", str(DESTINATION / "rotated.mov")])
    run(common + ["-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "log-level=error", "-tag:v", "hvc1",
                  "-pix_fmt", "yuv420p", "-c:a", "aac", str(DESTINATION / "hevc.mov")])
    print(f"Browser video fixtures generated in {DESTINATION}")


if __name__ == "__main__":
    main()
