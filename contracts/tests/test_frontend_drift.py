"""ADR-009: the frontend's hand-written mirror of the contract must not drift.

`frontend/src/types/contracts.ts` mirrors `mars_contracts` by hand. Adding
`EndpointPrediction.model_id` (ADR-017) and `ad_threshold` (ADR-020) each meant
touching the contract, the service and this mirror at once, with nothing to say
a miss. This compares what the mirror *names* — enum members and interface
field names — against the Pydantic models. It does not compare types: a type
check would need a real TS parser, and the failure that has actually happened is
a missing or renamed field.
"""

import re
from pathlib import Path

import pytest
from mars_contracts import (
    BatchPredictResponse,
    BatchRowResult,
    CompareRequest,
    CompareResponse,
    DeleteAccountRequest,
    DepictRequest,
    Endpoint,
    EndpointCategory,
    EndpointPrediction,
    GenerationsResponse,
    LimitsResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    MoleculeProperties,
    PasswordResetConfirmRequest,
    PasswordResetRequestModel,
    PredictionRequest,
    PredictionResponse,
    RegisterRequest,
    RegisterResponse,
    SavedMoleculeResponse,
    SavedReportResponse,
    SaveMoleculeRequest,
    SaveReportRequest,
    StructuralAlert,
    TaskType,
)

TS_PATH = Path(__file__).resolve().parents[2] / "frontend" / "src" / "types" / "contracts.ts"

pytestmark = pytest.mark.skipif(not TS_PATH.exists(), reason="frontend/ not present in this checkout")


def _ts() -> str:
    return TS_PATH.read_text(encoding="utf-8")


def _ts_union(name: str) -> set[str]:
    m = re.search(rf"export type {name}\s*=(.*?);", _ts(), re.S)
    assert m, f"`export type {name}` not found in contracts.ts"
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def _ts_interface_fields(name: str) -> set[str]:
    m = re.search(rf"export interface {name}\s*\{{(.*?)^\}}", _ts(), re.S | re.M)
    assert m, f"`export interface {name}` not found in contracts.ts"
    body = re.sub(r"//[^\n]*", "", m.group(1))
    # a field starts at the beginning of a line: `name:` or `name?:`
    return set(re.findall(r"^\s*([a-z_][a-z0-9_]*)\??\s*:", body, re.M))


@pytest.mark.parametrize("ts_name,enum", [("Endpoint", Endpoint), ("TaskType", TaskType), ("EndpointCategory", EndpointCategory)])
def test_enum_members_match(ts_name, enum):
    assert _ts_union(ts_name) == {e.value for e in enum}


@pytest.mark.parametrize(
    "ts_name,model",
    [
        ("PredictionRequest", PredictionRequest),
        ("EndpointPrediction", EndpointPrediction),
        ("PredictionResponse", PredictionResponse),
        ("MoleculeProperties", MoleculeProperties),
        ("StructuralAlert", StructuralAlert),
        ("BatchRowResult", BatchRowResult),
        ("BatchPredictResponse", BatchPredictResponse),
        ("CompareRequest", CompareRequest),
        ("CompareResponse", CompareResponse),
        ("DepictRequest", DepictRequest),
        ("GenerationsResponse", GenerationsResponse),
        ("LimitsResponse", LimitsResponse),
        ("MeResponse", MeResponse),
        ("LoginRequest", LoginRequest),
        ("LoginResponse", LoginResponse),
        ("RegisterRequest", RegisterRequest),
        ("RegisterResponse", RegisterResponse),
        ("SaveMoleculeRequest", SaveMoleculeRequest),
        ("SaveReportRequest", SaveReportRequest),
        ("SavedMoleculeResponse", SavedMoleculeResponse),
        ("SavedReportResponse", SavedReportResponse),
        ("DeleteAccountRequest", DeleteAccountRequest),
        ("PasswordResetRequestModel", PasswordResetRequestModel),
        ("PasswordResetConfirmRequest", PasswordResetConfirmRequest),
    ],
)
def test_interface_fields_match(ts_name, model):
    assert _ts_interface_fields(ts_name) == set(model.model_fields)


def test_classification_value_is_not_called_a_probability():
    # ADR-023: the 0-1 classification output is a score. The contract description and its
    # frontend mirror must say so; "probability" may only appear negated ("not a ... probability").
    desc = EndpointPrediction.model_fields["value"].description or ""
    assert "score" in desc
    assert "probability" not in desc.replace("not a validated probability", "")
    mirror = re.search(r"export interface EndpointPrediction\s*\{(.*?)^\}", _ts(), re.S | re.M).group(1)
    assert "classification score" in mirror
    assert "probability" not in mirror.replace("not a validated probability", "")
