# Stage 1: build the frontend bundle. Same origin as the API (ADR-025), so the base is /api.
FROM node:20-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/index.html frontend/tsconfig.json frontend/tsconfig.node.json frontend/vite.config.ts ./
COPY frontend/src ./src
ENV VITE_API_BASE=/api
RUN npm run build

# Stage 2: the API, with the bundle beside it.
FROM python:3.11-slim

WORKDIR /app

# RDKit's 2D drawing module (POST /depict, frontend ADR-039) links against these; python:3.11-slim has none of them, and
# without them `from rdkit.Chem.Draw import rdMolDraw2D` fails to import, so /depict answers 501 in the built image.
# Checked 2026-10-23: this exact set is enough (no libsm6, no libx11 beyond what libxrender1 pulls in).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libxrender1 libxext6 libexpat1 \
    && rm -rf /var/lib/apt/lists/*

COPY contracts /contracts
COPY api/requirements.txt ./requirements.txt
COPY ml/requirements-serving.txt ./requirements-ml-serving.txt

# api/requirements.txt = API/auth/persistence deps.
# requirements-ml-serving.txt = the minimal ml/ subset (rdkit, xgboost, numpy)
# needed to run REAL inference (ml/serve/) instead of falling back to the
# Module 8 stub for every endpoint. Deliberately excludes training-only deps
# (pandas, scikit-learn, scipy, wandb, pytest) and GPU deps (torch/KERMT) —
# see ml/requirements-serving.txt for the full rationale.
RUN pip install --no-cache-dir -e /contracts \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-ml-serving.txt

COPY api/app ./app
COPY --from=frontend /frontend/dist ./static
ENV STATIC_DIR=/app/static
# ml/ subset the serving path actually imports (serve/, featurize/, models/,
# eval/) — NOT ml/data (training-only loaders), ml/train, ml/tracking,
# ml/tests, ml/runs, ml/.venv. Trained artifacts (ml/artifacts/) are mounted
# as a volume in docker-compose, not baked into the image — they change
# independently of code.
COPY ml/serve ./ml/serve
COPY ml/featurize ./ml/featurize
COPY ml/models ./ml/models
COPY ml/eval ./ml/eval
COPY ml/explain ./ml/explain
ENV PYTHONPATH=/app/ml

EXPOSE 8000

# Cloud Run supplies $PORT; 8000 is the local default. Production also sets SESSION_COOKIE_SECURE=true
# (the app warns at start-up if it serves the bundle without it) and leaves CORS_ALLOW_ORIGINS empty.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]