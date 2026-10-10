# Pose extraction performance

## Configuration

The default remains **Full / 30 FPS**, because reduced-cadence and Lite trials
did not pass all measurement-regression checks.

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `MEDIAPIPE_MODEL_COMPLEXITY` | `1` | `0` = Lite, `1` = Full, `2` = Heavy |
| `MEDIAPIPE_TARGET_FPS` | `30` | Requested extraction rate, between 1 and 60 FPS |
| `OPENCV_NUM_THREADS` | OpenCV default | Optional native thread-pool override; benchmark before setting |

All three models are packaged by both Dockerfiles. Environment overrides must
be set on the backend container before startup. For example, an experimental
Full / 20 configuration uses `MEDIAPIPE_MODEL_COMPLEXITY=1` and
`MEDIAPIPE_TARGET_FPS=20`.

## Implemented changes

- Decode with `grab()` and retrieve images only when selected for inference.
  This avoids materializing discarded images, but still decodes compressed
  reference frames needed by the codec.
- Select frames on a timestamp clock instead of rounding a source-frame stride.
  A 30 FPS input requested at 20 FPS now produces approximately 20 samples/sec,
  rather than 15. Near-target inputs such as nominal 30 FPS with 30.03 metadata
  retain all frames to avoid dropping isolated tracking frames.
- Preserve presentation timestamps with a nominal-FPS fallback for decoders
  that do not expose them. Track source-frame indices and each sample's duration.
- Make smoothing, peak windows, fallback segmentation, and one-second active-set
  padding duration-aware. OneEuro filters continue to use elapsed time.
- Resample video output onto a constant-rate clock while holding the latest
  selected image and pose. No synthetic joints enter measurements. Encoded
  duration is preserved to within one output frame.
- Use timestamps for 3D playback and seeking, including catching up after
  animation stalls. Legacy records retain an FPS fallback.
- Build display-only occlusion interpolation in linear time, using timestamps.
- Keep zero-confidence joints excluded from measurements (previously `0.0`
  was accidentally treated as a missing confidence value and promoted to 1.0).

## Production profiling

Each upload logs `Extraction profile` and persists it under
`raw_timeseries_data.extraction_profile`. It contains model, requested/effective
sampling rates, source resolution/FPS/duration, inference count, OpenCV thread
count, and time spent in detector initialization, decoding, preprocessing,
inference, filtering, and display interpolation. Client trimming is timed
separately in the backend logs.

Collect these profiles on the Azure **1 CPU / 2 GiB** instance for both isolated
uploads and uploads while a previous overlay is rendering. Rendering runs off
the results critical path but still shares the container's CPU.

## Reproducible benchmark

Run from the repository root with the four existing benchmark clips available:

```bash
python backend/tests/benchmark_pose_sampling.py --original-baseline --one-core --repeats 2 --output data/pose_sampling_benchmark.json
```

`--original-baseline` loads extractor and analysis source from the current git
`HEAD`; use it while the optimization changes are uncommitted, or when `HEAD`
is the intended comparison revision. Without it, Full / 30 in the current
working tree is the reference. Missing clips are errors, not skipped passes.

Use `--configs full_30 full_20` for a focused comparison. Add `--require-pass`
to require a faster configuration that passes both regression and human-count
checks. An explicit OpenCV setting can be tested by setting
`OPENCV_NUM_THREADS` before launching the benchmark.

### Local results, 2026-10-07

Windows Python 3.14.3, MediaPipe 0.10.35, OpenCV 5.0.0; process restricted to one
logical CPU. These are local measurements, **not Azure latency guarantees**.
Each entry sums the median extraction times over four clips, with two runs per
configuration. The original Full / 30 reference summed to **42.28 seconds**.

| Configuration | Extraction total | Speedup vs original | Measurement regression |
| --- | ---: | ---: | --- |
| Full / 30 | 42.69 s | 0.99× | Pass on all clips |
| Full / 25 | 35.17 s | 1.20× | Fail |
| Full / 20 | 29.65 s | 1.43× | Fail |
| Lite / 30 | 33.31 s | 1.27× | Fail |
| Full / 15 | 21.57 s | 1.96× | Fail |
| Lite / 20 | 23.14 s | 1.83× | Fail |

All configurations retained the human-labelled total counts: **21 reps**.
This alone did not establish measurement equivalence. Full / 20 reduced
extraction time about **30%**, but some measurements/classifications changed
beyond the gates. Full / 25 was also not a passing compromise. Therefore no
lower-cadence or Lite configuration has been promoted to the default.

The Full reference also classified only **1 full rep instead of the labelled
3** in `lat_pulldown_online_log57.mp4`; this disagreement existed before these
changes. Lite matched the labelled counts but changed other measurements.

The OpenCV one-thread experiment was not a reliable aggregate improvement;
it remains an opt-in tuning setting. The supplied clips are approximately
30 FPS, so they do not demonstrate the selective-retrieval benefit on
60/120-FPS phone inputs.

### Regression gates

The benchmark checks every repeat against the reference:

- Identical total and full/partial counts.
- Rep boundary and phase-tempo differences no greater than 0.10 seconds.
- Per-rep mean-velocity difference no greater than 5%.
- ROM differences no greater than 5 percentage points.
- Per-rep flare/shoulder-tilt differences no greater than 5 degrees.
- Velocity-loss difference no greater than 5 percentage points.
- Stable partial/asymmetry/shoulder-side, RPE/RIR, and fatigue classifications.

These are conservative regression tolerances, not independent accuracy ground
truth. Add representative fast-rep, occluded, trimmed, and 60/120-FPS phone clips
before promoting a setting. The raw JSON output includes per-clip gate failures
and maximum errors, so a faster result cannot hide changed measurements.
