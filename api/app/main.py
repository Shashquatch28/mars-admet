from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health, predict

app = FastAPI(
    title="MARS API",
    description="Molecular ADMET Rapid Screening — prediction, batch, and molecule-detail serving.",
    version="0.1.0-dev",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before prod deploy
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(predict.router, prefix="/predict", tags=["predict"])
