import os
import urllib.request

# Benchmark video URLs are configured via environment variables to avoid exposing personal workout clips.
# In local development, you can set these variables or directly place the MP4 clips in data/benchmark_videos/.
BENCHMARK_VIDEOS = {
    "lat_pulldown_online_log64.mp4": os.getenv("BENCHMARK_PULLUP_LOG64_URL"),
    "pullup_online_log63.mp4": os.getenv("BENCHMARK_PULLUP_LOG63_URL"),
    "pullup_online_log61.mp4": os.getenv("BENCHMARK_PULLUP_LOG61_URL"),
    "lat_pulldown_online_log57.mp4": os.getenv("BENCHMARK_LAT_PULLDOWN_LOG57_URL"),
}

def download_benchmarks():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    out_dir = os.path.join(base_dir, "data", "benchmark_videos")
    os.makedirs(out_dir, exist_ok=True)

    print(f"Checking benchmark video clips in {out_dir}...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for filename, url in BENCHMARK_VIDEOS.items():
        dest = os.path.join(out_dir, filename)
        if os.path.exists(dest) and os.path.getsize(dest) > 1000:
            print(f"[EXISTS] {filename} ({os.path.getsize(dest)/(1024*1024):.2f} MB)")
            continue

        if not url:
            print(f"[SKIP] No URL configured for {filename}. Set environment variable or place file in {out_dir}.")
            continue

        print(f"[DOWNLOADING] {filename} from {url}...")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as f:
                f.write(resp.read())
            print(f"[SAVED] {filename} ({os.path.getsize(dest)/(1024*1024):.2f} MB)")
        except Exception as e:
            print(f"[ERROR] Failed to download {filename}: {e}")

if __name__ == "__main__":
    download_benchmarks()
