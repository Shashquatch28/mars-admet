FROM python:3.11-slim

WORKDIR /app

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
# ml/ subset the serving path actually imports (serve/, featurize/, models/,
# eval/) — NOT ml/data (training-only loaders), ml/train, ml/tracking,
# ml/tests, ml/runs, ml/.venv. Trained artifacts (ml/artifacts/) are mounted
# as a volume in docker-compose, not baked into the image — they change
# independently of code.
COPY ml/serve ./ml/serve
COPY ml/featurize ./ml/featurize
COPY ml/models ./ml/models
COPY ml/eval ./ml/eval
ENV PYTHONPATH=/app/ml

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]