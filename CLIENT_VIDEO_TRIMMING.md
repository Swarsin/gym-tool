# Pre-upload video trimming

## User flow

1. Select a video and choose a range in the existing trimmer.
2. The application shows **Preparing selected clip** and runs a dedicated worker.
3. The worker rewrites the selected section into a new MP4, preserving the
   recorded video/audio packets, dimensions, rotation, and frame timing.
4. Only the resulting file is uploaded. The analysis request sends
   `trim_start_s: null` and `trim_end_s: null`, so the backend does not re-encode
   the selected range a second time.

**Analyze Entire Video** bypasses preparation. Selecting the complete range also
avoids an unnecessary conversion.

## Lossless preparation

Mediabunny 1.61.3 runs in a same-origin module worker. Preparation uses its forced
packet-copy path rather than browser video encoding. This preserves the source
images and works without requiring a browser video encoder, FFmpeg/WASM, or
cross-origin-isolation headers.

MP4 edit lists describe the visible range. Compressed reference packets around
keyframes may be retained because they are necessary to decode selected frames;
they are not part of the displayed clip. The visible end is checked within one
source-frame tolerance. File-size reduction depends on the selected range and
keyframe spacing; this feature does not resize or lower the bitrate of the video.

The worker rejects unreadable/missing tracks, tracks that cannot be copied,
changed dimensions/codecs, inaccurate output duration, empty output, and output
over 150 MiB. Source files retain the existing 150 MiB selection limit.

The source player is normally used to obtain duration. If native preview is
unsupported, the application reads container metadata separately, allowing the
user to select times even without a playable preview.

## Explicit server fallback

If a local lossless cut cannot be produced, the application pauses before any
upload. It offers **Retry on device**, **Upload original & trim on server**, or
**Cancel**. Only the explicit server option uploads the original and passes the
original trim timestamps to the backend. Some HEVC/B-frame cuts cannot satisfy
the strict duration guard and use this fallback.

The application-level upload controller survives the upload form unmounting.
Cancellation terminates the worker, aborts pending network requests, and ignores
late completions. An aborted R2 request never starts a storage-provider fallback
or dispatches a new analysis. The existing Supabase storage fallback receives
the same prepared file and uses an operation-scoped fetch signal; the shared
authentication client is not changed.

Worker preparation is bounded to 120 seconds; metadata reading and API replies
to 30 seconds, and individual storage requests to 180 seconds. A cancellation
after an analysis request has already reached the server does not cancel the
server's background job.

## Verification

### Fast tests and build

From `frontend/`, with Node.js 22+:

```bash
npm test
npm run typecheck
npm run build
```

The Node tests cover preparation before upload, prepared-file selection,
explicit fallback, retry, cancellation during preparation/upload/response-body
reading, stale completions, duplicate submissions, worker failures/timeouts,
input limits, and invalid analysis IDs.

### Real browser tests

Generate reproducible media fixtures from the repository root:

```bash
python backend/tests/generate_trim_fixtures.py
```

Then, from `frontend/`:

```bash
npx playwright install chromium firefox webkit
npm run test:browser:all
```

An installed Chrome can be used by setting `PLAYWRIGHT_CHANNEL=chrome`.
The test configuration launches isolated local Vite/API/storage fixtures with
dummy credentials; it never uploads to the production backend or cloud storage.
Generated media, browser results, and traces are ignored by git.

Tests verify the actual uploaded bytes with a local HTTP receiver, null backend
trim fields, both storage paths, explicit fallback, cancellation, MP4/WebM/MOV,
variable frame timing, portrait rotation, and the built production worker. HEVC
either preserves the recording or takes the explicit fallback. Testing the
WebKit engine does not replace testing a physical iPhone/Safari installation.

### Lifting footage and exact decoded-frame fidelity

With the four existing files in `data/benchmark_videos/`, run from `frontend/`:

```bash
CLIENT_TRIM_BENCHMARK=1 npx playwright test --project=chromium --grep="exercise benchmark"
```

PowerShell users can set `$env:CLIENT_TRIM_BENCHMARK = '1'` before running the
Playwright command. Then, from the repository root:

```bash
python backend/tests/benchmark_client_trim.py --results-dir frontend/test-results --fidelity
```

The fidelity check compares SHA-256 hashes of **every full-resolution decoded
frame** against the selected original frames. All four clips passed locally:

| Clip | Selected source frames | Decoded clip frames | Exact pixels |
| --- | ---: | ---: | --- |
| `lat_pulldown_online_log57.mp4` | 484 | 484 | Pass |
| `lat_pulldown_online_log64.mp4` | 381 | 381 | Pass |
| `pullup_online_log61.mp4` | 441 | 441 | Pass |
| `pullup_online_log63.mp4` | 531 | 531 | Pass |

These rows are the Chrome run. Firefox and WebKit outputs also passed all four
fidelity checks (small native-duration rounding differences can select one more
or fewer final frames). Select their outputs using `--browser firefox` or
`--browser webkit`. Final verification passed **21 Node tests**, **48 browser
tests** across the three engines, type checking, and the production build.

Cached desktop Chrome preparation took approximately **0.12–0.22 seconds** for
these clips. This is preparation time, not a measured end-to-end Azure speedup.

Without `--fidelity`, the comparison script measures differences against the
old server's lossy FFmpeg re-encode. That strict measurement comparison did not
pass on these four clips: the pose/FSM pipeline is sensitive to the different
pixels/timing produced by that re-encode. The new path preserves the original
selected images exactly; it does not promise identical measurements to a lossy
transcoded input. `--inspect` reports decoded counts and image correspondence
without running MediaPipe, useful because container frame counts may include
hidden codec-reference packets.

## Deployment

Deploy the frontend build, including the emitted `trimVideo.worker-*.js` asset
and the lazy metadata-reader chunk. The backend API needs no new fields or
migrations. If the worker cannot be loaded, users get the explicit fallback
instead of an automatic original-file upload.
