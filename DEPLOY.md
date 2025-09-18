FloatChat Backend Deployment Guide

Goal: Host the FastAPI backend so your Vercel frontend can call it via CORS.

Prereqs
- Python 3.11 or Docker
- Supabase Postgres creds (if using Postgres) or SQLite for demo
- Environment variables: see .env (do not commit secrets)

Important envs
- API_PREFIX=/api
- CORS_ORIGINS=comma-separated: e.g. https://your-frontend.vercel.app,http://localhost:5173
- GEMINI_API_KEY=your_key
- GEMINI_MODEL=gemini-1.5-flash

Option A: Render.com (no Docker)
1) Create new Web Service from your GitHub repo, root set to flotchat-backend
2) Runtime: Python 3.11
3) Build Command: pip install -r requirements.txt
4) Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
5) Add Env Vars: copy from .env (replace CORS_ORIGINS with your Vercel URL)
6) Deploy. Note your public base URL, e.g. https://floatchat-api.onrender.com
7) In frontend .env: VITE_API_URL=https://floatchat-api.onrender.com

Option B: Railway.app (no Docker)
1) Create New Service -> Deploy from Repo -> Path = flotchat-backend
2) Nixpacks auto-detects Python. Set Start Command similar to Render
3) Add env vars
4) Deploy and copy the URL -> set VITE_API_URL in frontend

Option C: Google Cloud Run (Docker)
1) Build image locally or with Cloud Build
   docker build -t gcr.io/PROJECT/floatchat-backend -f flotchat-backend/Dockerfile .
   docker push gcr.io/PROJECT/floatchat-backend
2) Deploy to Cloud Run (fully managed)
   Set container port 8000, allow unauthenticated
3) Add env vars in Cloud Run service -> Variables & Secrets
4) Copy URL and set VITE_API_URL

Option D: Fly.io (Docker)
1) fly launch --path flotchat-backend --dockerfile flotchat-backend/Dockerfile
2) fly secrets set GEMINI_API_KEY=... CORS_ORIGINS=https://your-frontend.vercel.app
3) fly deploy

CORS
- Ensure CORS_ORIGINS includes your Vercel domain. Wildcard * disables credentials and is fine for public GET endpoints, but for POST/chat use specific origins.

Frontend wiring
- In flotchat-frontend/.env: VITE_API_URL=https://your-backend
- Redeploy Vercel after updating envs

Health checks
- GET /api/health -> {"status":"ok"}
- GET /api/argo/stats
- POST /api/chat/query {"message":"hello"}

Troubleshooting
- 403/Failed CORS: confirm your origin matches exactly (https scheme, no trailing slash)
- 500 on chat: ensure GEMINI_API_KEY set and billing enabled
- Timeouts on NetCDF: server has outbound internet and port 443 open
