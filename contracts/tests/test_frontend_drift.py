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
    DescriptorAttribution,
    Endpoint,
    EndpointCategory,
    EndpointPrediction,
    ExplainJobState,
    ExplainJobStatus,
    ExplainMethod,
    ExplainOutputSpace,
    ExplainResponse,
    FragmentAttribution,
    GenerationsResponse,
    LimitsResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    MoleculeProperties,
    NameRequest,
    NameResponse,
    NameStatus,
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


@pytest.mark.parametrize(
    "ts_name,enum",
    [
        ("Endpoint", Endpoint),
        ("TaskType", TaskType),
        ("EndpointCategory", EndpointCategory),
        ("ExplainMethod", ExplainMethod),
        ("ExplainOutputSpace", ExplainOutputSpace),
        ("ExplainJobState", ExplainJobState),
        ("NameStatus", NameStatus),
    ],
)
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
        ("NameRequest", NameRequest),
        ("NameResponse", NameResponse),
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
        ("ExplainResponse", ExplainResponse),
        ("ExplainJobStatus", ExplainJobStatus),
        ("FragmentAttribution", FragmentAttribution),
        ("DescriptorAttribution", DescriptorAttribution),
    ],
)
def test_interface_fields_match(ts_name, model):
    assert _ts_interface_fields(ts_name) == set(model.model_fields)


def test_explain_contract_never_speaks_of_risk_or_favourability():
    # ADR-031 / AGENTS.md rule 1: attribution is "pushed up / pushed down", never a judgement.
    banned = re.compile(r"\b(risk|risky|safe|safety|toxic|toxicity|favourable|favorable|unfavourable|good|bad|better|worse)\b", re.I)
    texts: list[str] = []
    for model in (ExplainResponse, ExplainJobStatus, FragmentAttribution, DescriptorAttribution):
        texts.extend(f.description or "" for f in model.model_fields.values())
    joined = " ".join(texts)
    assert not banned.findall(joined), banned.findall(joined)
    mirror = re.search(r"// --- explanation.*?// --- batch", _ts(), re.S).group(0)
    mirror = mirror.replace('never good or bad', "")
    assert not banned.findall(mirror), banned.findall(mirror)


def test_classification_value_is_not_called_a_probability():
    # ADR-023: the 0-1 classification output is a score. The contract description and its
    # frontend mirror must say so; "probability" may only appear negated ("not a ... probability").
    desc = EndpointPrediction.model_fields["value"].description or ""
    assert "score" in desc
    assert "probability" not in desc.replace("not a validated probability", "")
    mirror = re.search(r"export interface EndpointPrediction\s*\{(.*?)^\}", _ts(), re.S | re.M).group(1)
    assert "classification score" in mirror
    assert "probability" not in mirror.replace("not a validated probability", "")
