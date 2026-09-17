from __future__ import annotations

from fastapi import APIRouter, HTTPException
from mars_contracts import CompareRequest, CompareResponse

from app.services.prediction_service import predict as predict_one

router = APIRouter()


@router.post("", response_model=CompareResponse)
def compare(req: CompareRequest) -> CompareResponse:
    try:
        molecules = [predict_one(smiles, req.endpoints) for smiles in req.smiles]
    except ValueError as exc:
        # Same Module 3 Stage 1 validation as /predict (real ml stack only) —
        # a single invalid SMILES fails the whole comparison rather than
        # silently comparing against a fabricated result.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # per_endpoint_winner resolution table (direction-of-good per endpoint) is
    # an M3/M4 UI decision per contracts/api.py's own docstring — left None.
    return CompareResponse(molecules=molecules, per_endpoint_winner=None)
