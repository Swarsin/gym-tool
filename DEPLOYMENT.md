# 🚀 Production Deployment Guide

Guide to deploying the full-stack AI Biomechanics & Velocity-Based Training (VBT) platform.

---

## 🏗️ Architecture Overview

* **Frontend**: React 18 + Vite + Tailwind CSS + Lucide $\to$ Hosted on **[Vercel](https://vercel.com)**
* **Backend**: Python 3.11 + FastAPI + MediaPipe + OpenCV + FFmpeg $\to$ Hosted on **[Azure Container Apps](https://azure.microsoft.com/en-us/products/container-apps)**
* **Database & Auth**: PostgreSQL with Row-Level Security (RLS) & JWT Auth $\to$ Hosted on **[Supabase](https://supabase.com)**
* **Object Storage**: High-speed S3-compatible video storage $\to$ Hosted on **[Cloudflare R2](https://www.cloudflare.com/developer-platform/r2/)**

---

## Step 1: Environment Variables

Configure your secrets in your hosting environments (or `.env` locally). Never commit live credentials to source control.

### Backend Environment Variables

| Variable Name | Description | Example Placeholder |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string (asyncpg) | `postgresql+asyncpg://postgres:[PASSWORD]@[HOST]:5432/postgres` |
| `GEMINI_API_KEY` | Google Gemini API key for AI coaching agent | `your-gemini-api-key` |
| `SUPABASE_URL` | Supabase project URL | `https://your-project.supabase.co` |
| `SUPABASE_ANON_KEY` | Supabase public anonymous API key | `your-supabase-anon-key` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (optional backend-only) | `your-supabase-service-role-key` |
| `R2_ACCOUNT_ID` | Cloudflare account ID | `your-cloudflare-account-id` |
| `R2_ACCESS_KEY_ID` | Cloudflare R2 S3 access key ID | `your-r2-access-key-id` |
| `R2_SECRET_ACCESS_KEY` | Cloudflare R2 S3 secret access key | `your-r2-secret-access-key` |
| `R2_BUCKET_NAME` | Cloudflare R2 bucket name | `workout-videos` |
| `R2_PUBLIC_URL` | Cloudflare R2 public bucket domain | `https://pub-your-bucket.r2.dev` |
| `FRONTEND_URL` | Allowed frontend origin for CORS | `https://your-gym-app.vercel.app` |

### Frontend Environment Variables (`frontend/.env`)

| Variable Name | Description | Example Placeholder |
|---|---|---|
| `VITE_SUPABASE_URL` | Supabase project URL | `https://your-project.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | Supabase public anonymous API key | `your-supabase-anon-key` |
| `VITE_API_BASE_URL` | Backend API base URL | `https://your-backend.azurecontainerapps.io` |

---

## Step 2: Backend Deployment (Azure Container Apps)

The backend is packaged into a container with OpenCV, MediaPipe, and FFmpeg dependencies.

### Automated CI/CD (GitHub Actions)

When pushing to `main`, `.github/workflows/deploy.yml` automatically:
1. Runs the fast offline Python test suite (`python -m unittest discover -s backend/tests -p "test_*.py"`).
2. Builds the Docker container image.
3. Pushes to Azure Container Registry (ACR).
4. Deploys the revision to Azure Container Apps.

Configure these GitHub Actions Repository Secrets:
* `ACR_PASSWORD`: Azure Container Registry admin password
* `AZURE_CLIENT_ID`: Azure Service Principal client ID
* `AZURE_TENANT_ID`: Azure Active Directory tenant ID
* `AZURE_SUBSCRIPTION_ID`: Azure subscription ID

---

## Step 3: Frontend Deployment (Vercel)

1. Connect your repository to **[Vercel](https://vercel.com)**.
2. In Project Settings:
   * **Framework Preset**: `Vite`
   * **Root Directory**: `frontend`
3. Add the three frontend environment variables:
   * `VITE_SUPABASE_URL`
   * `VITE_SUPABASE_ANON_KEY`
   * `VITE_API_BASE_URL`
4. Click **Deploy**.

---

## Step 4: Local Development

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Or on Windows: .venv\Scripts\activate
pip install -r requirements.txt
python start.py
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```
