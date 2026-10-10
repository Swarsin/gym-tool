# 🏋️ AI Biomechanics & Velocity-Based Training (VBT) Platform

A full-stack, cloud-native computer vision platform that provides real-time biomechanical analysis, repetition segmentation, 3D joint kinematics, and AI-driven coaching for resistance training.

---

## 🌟 Highlights

* **Kinematic Rep Segmentation**: 4-State Finite State Machine (FSM) detecting concentric, isometric peak, and eccentric phases with flutter-rejection.
* **Velocity-Based Training (VBT)**: Multi-segment anthropometric scale calibration, mean/peak concentric velocity, velocity loss %, and dynamic RPE/RIR estimations.
* **3D Interactive Joint Viewer**: Interactive Three.js skeleton visualizer rendering real-time elbow flare, shoulder tilt, and bilateral symmetry metrics synced to video playback.
* **Bilateral Asymmetry & Fatigue Drift**: Analyzes left vs. right pull imbalances, shoulder hiking, and progressive motor pattern degradation under heavy fatigue.
* **AI Hypertrophy Coach**: LLM agent (Google Gemini) delivering structured form critiques, anatomical muscle recruitment analysis, and actionable corrective cues.
* **Progressive Async Pipeline**: Returns measurements and the 3D skeleton first, then AI coaching and an annotated video overlay as their background tasks finish.
* **Hardened Security**: Strict JWT authentication, approved-storage SSRF protection, MIME type validation, and authenticated Cloudflare R2 presigned URLs.

---

## 🏗️ System Architecture

```
[User / Browser]
       │
       ▼  (React 18 + Vite + Tailwind + Three.js)
┌────────────────────────────────────────────────────────┐
│ 1. Video Trimmer & Authenticated Upload to Cloudflare R2│
└────────────────────────────────────────────────────────┘
       │
       ▼  (POST /api/v1/analyze)
┌────────────────────────────────────────────────────────┐
│ 2. FastAPI Backend (Azure Container Apps)              │
│    ├─ Pose Extraction: MediaPipe Pose Landmarker      │
│    ├─ Signal Smoothing: Adaptive 1-Euro Filter         │
│    ├─ Kinematics Engine: 4-State Finite State Machine │
│    ├─ VBT Calibrator: Pixel-to-Meter Anthropometry    │
│    └─ Bilateral Imbalance & Fatigue Drift Analyzer    │
└────────────────────────────────────────────────────────┘
       │
       ├─────────────────────────────────┐
        ▼ (Progressive Results)          ▼ (Async Background)
┌───────────────────────────────┐ ┌──────────────────────────────┐
│ Gemini AI Coaching Agent      │ │ Single-Pass Video HUD Engine │
│ ├─ Form Scorecard (0-100)     │ │ ├─ OpenCV Landmark HUD       │
│ ├─ Primary Biomechanical Flaw │ │ ├─ Real-Time Speedometer     │
│ └─ Progressive Overload Cues  │ │ └─ FFmpeg H.264 Encoder      │
└───────────────────────────────┘ └──────────────────────────────┘
       │                                 │
       ▼                                 ▼
┌────────────────────────────────────────────────────────┐
│ PostgreSQL (Supabase) + Cloudflare R2 Storage CDN      │
└────────────────────────────────────────────────────────┘
```

---

## 🔬 Core Engineering Innovations

### 1. Kinematic Finite State Machine (FSM)
Repetition detection avoids naive peak-finding thresholds that fail on lifters with partials or shaking under fatigue. The engine models rep phases as a 4-state transition graph:
* **State 0 (Valley Tracking)**: Tracks lowest inflection point and filters micro-jitters before concentric departure.
* **State 1 (Concentric Drive)**: Tracks upward travel velocity and verifies displacement exceeds dynamic threshold ($0.22 \times \text{dynamic range}$).
* **State 2 (Peak Contraction)**: Detects velocity reversal and enforces isometric hold duration.
* **State 3 (Eccentric Control)**: Hardened against velocity micro-flutters, verifying meaningful descent before concluding the repetition.

### 2. Velocity-Based Training (VBT) Calibration
* **Spatial Calibration**: Estimates meters-per-coordinate using user height and anatomical segment ratios (torso, arm, femur lengths).
* **Velocity Loss Tracking**: Calculates fatigue drop-off across the set:
  $$\text{Loss } \% = \frac{V_{\max} - V_{\text{final}}}{V_{\max}} \times 100$$
* **RIR & RPE Prediction**: Maps velocity decay to Proximity-to-Failure (Repetitions In Reserve).

### 3. Bilateral Asymmetry Heatmaps
Calculates frame-by-frame 3D vectors for:
* Left vs. right elbow flare degrees ($\Delta \theta$).
* Scapular elevation / shoulder tilt.
* Flags "Fatigue Drift" when asymmetry escalates by $>4^\circ$ in the second half of a set.

---

## 🛠️ Tech Stack

| Domain | Technology |
|---|---|
| **Frontend** | React 18, Vite, TypeScript, Tailwind CSS, Three.js, Lucide Icons |
| **Backend** | Python 3.11, FastAPI, Uvicorn, SQLAlchemy (Asyncpg), Pydantic v2 |
| **Computer Vision** | MediaPipe Pose Landmarker, OpenCV, FFmpeg, SciPy, NumPy |
| **AI / LLM** | Google Gemini (via LangChain Google GenAI) |
| **Database & Auth** | Supabase (PostgreSQL with Row-Level Security), Supabase Auth |
| **Storage & CDN** | Cloudflare R2 (S3-compatible presigned uploads) |
| **Cloud Hosting** | Azure Container Apps (Backend), Vercel (Frontend) |
| **CI/CD** | GitHub Actions (automated test runner and Docker container deployments) |

---

## 🔒 Security & Privacy

* **Strict Authentication**: Uploads, analysis, logs, and stats require authenticated Bearer JWT tokens. No shared guest accounts.
* **SSRF Protection**: Video analysis URLs are strictly validated against configured storage host allowlists (`SUPABASE_URL`, `R2_PUBLIC_URL`).
* **MIME & Key Validation**: Upload URLs enforce video MIME types (`video/mp4`, `video/quicktime`, `video/webm`) and generate cryptographically secure UUID object keys.
* **Restricted CORS**: Cross-Origin requests are locked to authorized origins with explicit HTTP methods (`GET`, `POST`, `DELETE`, `OPTIONS`).
* **Zero Credential Exposure**: All credentials, database connection strings, and storage secrets are managed strictly through environment variables.

---

## 🧪 Testing & Verification

The repository includes both fast offline unit test suites and ground-truth benchmark pipelines:

```bash
# 1. Fast offline unit tests (mocks external DB, Gemini, and R2)
python -m unittest discover -s backend/tests -p "test_*.py"

# 2. Offline pipeline edge-case tests
python backend/tests/test_pipeline_edge_cases.py

# 3. Security boundary tests (Auth, SSRF rejection, MIME validation)
python backend/tests/test_security_endpoints.py

# 4. Multi-video ground-truth accuracy benchmark (evaluated on real lifting clips)
python backend/tests/benchmark_pipeline.py

# 5. Pose sampling/model latency and measurement-regression matrix
python backend/tests/benchmark_pose_sampling.py --one-core --repeats 2
```

See [POSE_PERFORMANCE.md](POSE_PERFORMANCE.md) for sampling configuration,
production profiling, and measured speed/accuracy tradeoffs.
See [CLIENT_VIDEO_TRIMMING.md](CLIENT_VIDEO_TRIMMING.md) for actual on-device
range trimming before upload, browser support, fallback behavior, and tests.

* **Unit Test Suite**: 26 tests covering pipeline flow, sampling cadence, video duration, edge cases (zero reps, missing landmarks, asymmetry), and security boundaries.
* **Empirical Accuracy**: Benchmark suite achieves **100% rep count accuracy (21/21 reps)** across human-verified Lat Pulldown and Pull-Up video sets.

---

## 🚀 Getting Started Locally

### Prerequisites
* Python 3.11+
* Node.js 18+
* FFmpeg installed and available on `PATH`

### 1. Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure your environment
cp .env.example .env
# Edit .env with your Supabase, Gemini, and R2 credentials

# Start the FastAPI server
python start.py
```
Backend API will be live at `http://localhost:8000` (Interactive Swagger docs: `http://localhost:8000/docs`).

### 2. Frontend Setup
```bash
cd frontend
npm install

# Configure your environment
cp .env.example .env
# Edit .env with your VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY

# Start Vite dev server
npm run dev
```
Frontend will be live at `http://localhost:5173`.

---

## 📄 License
This project is licensed under the MIT License.
