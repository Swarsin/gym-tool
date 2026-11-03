"""
Targeted Video Downloader and Trimmer for FormAI.

Downloads and trims targeted exercise video segments without downloading full videos,
using yt-dlp with bundled static FFmpeg from imageio-ffmpeg.
"""
import os
import shutil
import subprocess
from typing import Optional, Dict, Any, List
import imageio_ffmpeg

from backend.ml.dataset_collector.manifest import ClipEntry, DatasetManifest


class VideoDownloader:
    """Downloader and preprocessor for video dataset ingestion."""

    def __init__(self, output_dir: str = "data/dataset"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

        # yt-dlp expects an executable named 'ffmpeg.exe' in PATH for range downloads
        bin_dir = os.path.dirname(self.ffmpeg_exe)
        standard_ffmpeg = os.path.join(bin_dir, "ffmpeg.exe")
        if not os.path.exists(standard_ffmpeg):
            try:
                shutil.copyfile(self.ffmpeg_exe, standard_ffmpeg)
            except Exception:
                pass
        if os.path.exists(standard_ffmpeg):
            self.ffmpeg_exe = standard_ffmpeg
        if bin_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")

    def get_clip_destination(self, entry: ClipEntry) -> str:
        """Returns the local path where this clip should be stored."""
        # Group clips into subdirectories by exercise to keep dataset organized
        safe_exercise = entry.exercise.replace("/", "_").replace(" ", "_").lower()
        exercise_dir = os.path.join(self.output_dir, safe_exercise)
        os.makedirs(exercise_dir, exist_ok=True)
        filename = entry.local_filename or f"{entry.clip_id}.mp4"
        return os.path.join(exercise_dir, filename)

    def download_clip(self, entry: ClipEntry, overwrite: bool = False) -> str:
        """
        Downloads and trims a single clip to the specified start/end timestamps.
        Returns the path to the trimmed video file.
        """
        dest_path = self.get_clip_destination(entry)

        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1024 and not overwrite:
            print(f"[EXISTS] {entry.clip_id} -> {dest_path}")
            return dest_path

        url = entry.source_url.strip()

        # Case 1: Local file source
        if os.path.exists(url) or url.startswith("file://"):
            local_src = url.replace("file://", "")
            return self._trim_local_video(local_src, dest_path, entry.start_time, entry.end_time)

        # Case 2: Direct HTTP/HTTPS MP4 link (not youtube/vimeo)
        if url.lower().endswith(".mp4") or "storage" in url.lower() or "r2.dev" in url.lower():
            return self._download_direct_mp4_trimmed(url, dest_path, entry.start_time, entry.end_time)

        # Case 3: YouTube / Web Video streaming platform via yt-dlp
        return self._download_with_ytdlp(entry, dest_path)

    def _trim_local_video(self, src: str, dest: str, start_s: float, end_s: float) -> str:
        """Trims a local video file using FFmpeg."""
        duration = end_s - start_s
        cmd = [
            self.ffmpeg_exe, "-y",
            "-ss", str(start_s),
            "-i", src,
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "aac",
            dest
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg trim failed: {res.stderr}")
        return dest

    def _download_direct_mp4_trimmed(self, url: str, dest: str, start_s: float, end_s: float) -> str:
        """Streams and trims a remote direct MP4 file with FFmpeg seeking."""
        duration = end_s - start_s
        cmd = [
            self.ffmpeg_exe, "-y",
            "-ss", str(start_s),
            "-i", url,
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "aac",
            dest
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Direct stream trim failed: {res.stderr}")
        return dest

    def _download_with_ytdlp(self, entry: ClipEntry, dest: str) -> str:
        """Downloads only the specified segment using yt-dlp range trimming."""
        import yt_dlp

        # Temp pattern for download
        temp_dir = os.path.dirname(dest)
        temp_dest_tmpl = os.path.join(temp_dir, f"{entry.clip_id}.%(ext)s")

        ydl_opts = {
            "ffmpeg_location": self.ffmpeg_exe,
            "download_ranges": yt_dlp.utils.download_range_func(None, [(entry.start_time, entry.end_time)]),
            "force_keyframes_at_cuts": True,
            "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best",
            "outtmpl": temp_dest_tmpl,
            "quiet": True,
            "no_warnings": True,
            "overwrites": True,
        }

        print(f"[FETCHING] {entry.clip_id} ({entry.start_time}s - {entry.end_time}s from {entry.source_url})...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([entry.source_url])

        # Ensure the final file matches `dest`
        if not os.path.exists(dest):
            # Locate file with different ext
            for ext in (".mp4", ".mkv", ".webm"):
                alt = os.path.join(temp_dir, f"{entry.clip_id}{ext}")
                if os.path.exists(alt):
                    if alt != dest:
                        # Convert/remux to mp4
                        self._remux_to_mp4(alt, dest)
                        try:
                            os.remove(alt)
                        except OSError:
                            pass
                    break

        if not os.path.exists(dest):
            raise FileNotFoundError(f"yt-dlp failed to produce output file: {dest}")

        print(f"[SAVED] {entry.clip_id} ({os.path.getsize(dest)/(1024*1024):.2f} MB)")
        return dest

    def _remux_to_mp4(self, src: str, dest: str) -> str:
        """Remuxes or re-encodes non-mp4 formats into standard H.264 mp4."""
        cmd = [
            self.ffmpeg_exe, "-y",
            "-i", src,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "aac",
            dest
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return dest

    def download_manifest(
        self,
        manifest: DatasetManifest,
        overwrite: bool = False,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Batch downloads all or a subset of clips in the manifest."""
        results = {
            "succeeded": [],
            "failed": [],
            "skipped": [],
        }

        entries = manifest.entries[:limit] if limit else manifest.entries
        print(f"\nInitiating batch download of {len(entries)} clips into '{self.output_dir}'...")

        for idx, entry in enumerate(entries, 1):
            dest = self.get_clip_destination(entry)
            print(f"[{idx}/{len(entries)}] {entry.clip_id} [{entry.exercise}]")

            if os.path.exists(dest) and os.path.getsize(dest) > 1024 and not overwrite:
                results["skipped"].append({"clip_id": entry.clip_id, "path": dest})
                continue

            try:
                saved_path = self.download_clip(entry, overwrite=overwrite)
                results["succeeded"].append({"clip_id": entry.clip_id, "path": saved_path})
            except Exception as e:
                print(f"  [ERROR] {entry.clip_id}: {e}")
                results["failed"].append({"clip_id": entry.clip_id, "error": str(e)})

        print(f"\nDownload Batch Complete: {len(results['succeeded'])} succeeded, "
              f"{len(results['skipped'])} existing/skipped, {len(results['failed'])} failed.")
        return results

