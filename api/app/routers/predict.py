from fastapi import APIRouter, HTTPException
from mars_contracts import PredictionRequest, PredictionResponse

from app.services.stub_predictor import predict_stub

router = APIRouter()


@router.post("", response_model=PredictionResponse)
def predict(req: PredictionRequest) -> PredictionResponse:
    if not req.smiles or not req.smiles.strip():
        raise HTTPException(status_code=422, detail="smiles must be a non-empty string")
    # TODO(A->B handoff): replace predict_stub with the real inference wrapper
    # once Module 4 checkpoints + routing table land (Phase 2, sync #1).
    return predict_stub(req.smiles, req.endpoints)
