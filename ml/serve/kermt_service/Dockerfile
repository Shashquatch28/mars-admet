# MARS KERMT inference image (CPU). Runs the Tier-0 finetuned checkpoints in-process
# behind a small HTTP service so the API image can stay torch-free.
#
# Build from the repository root:
#   docker build -f ml/serve/kermt_service/Dockerfile -t mars-kermt-infer .
#
# Differences from NVIDIA's training image (KERMT Dockerfile / environment.yml):
#   - CPU torch 2.9.1 (same version), no CUDA base image: serving is CPU-only (blueprint Module 10).
#   - rdkit pinned to 2025.09.1, the exact version the checkpoints were trained and evaluated
#     with (environment.yml). This is load-bearing: on 2025.9.6 the same checkpoint's CYP
#     probabilities drift by up to 4e-3 from the GPU reference, on 2025.09.1 by <= 4e-7
#     (parity_check.py, 2026-10-19), because rdkit_2d_normalized descriptors move between patch releases.
#   - cuik_molmaker is only imported by KERMT's featurizer module, not used (inference runs with
#     --use_cuikmolmaker_featurization off), so whichever version the solver picks alongside
#     rdkit 2025.09.1 is acceptable; parity_check.py is the guard.
#   - KERMT source is cloned at the exact commit recorded in every run's provenance
#     (e402473, tag v2.0.0) and verified; it is third-party Apache-2.0 code, not vendored here.
FROM condaforge/miniforge3:latest

ARG KERMT_COMMIT=e402473376ace30fa0092dad0578a88bf7f67287

RUN mamba create -y -n kermt -c conda-forge \
        python=3.11 \
        "pytorch=2.9.1=cpu*" \
        rdkit=2025.09.1 librdkit=2025.09.1 \
        cuik_molmaker \
        descriptastorus=2.7.0.4 \
        scikit-learn pandas tqdm tensorboard \
        "protobuf>=5.29.6" \
        "setuptools>=80.0.0,<82.0.0" \
        fastapi uvicorn \
    && mamba clean -afy

RUN git clone https://github.com/NVIDIA-BioNeMo/KERMT.git /opt/kermt \
    && git -C /opt/kermt checkout ${KERMT_COMMIT} \
    && test "$(git -C /opt/kermt rev-parse HEAD)" = "${KERMT_COMMIT}" \
    && rm -rf /opt/kermt/.git

ENV PATH=/opt/conda/envs/kermt/bin:$PATH \
    PYTHONPATH=/opt/kermt:/app/service \
    PYTHONUNBUFFERED=1 \
    KERMT_MODELS_DIR=/models

# Build context is the repository root.
COPY ml/serve/kermt_service/engine.py ml/serve/kermt_service/app.py ml/serve/kermt_service/parity_check.py ml/serve/kermt_service/explain_ig.py ml/serve/kermt_service/jobs.py /app/service/
# The torch-free half of Integrated Gradients (numpy only); the rest of ml/explain needs the API image's stack.
COPY ml/explain/__init__.py ml/explain/graph_ig.py /app/service/explain/

WORKDIR /app/service
EXPOSE 8100
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8100"]
