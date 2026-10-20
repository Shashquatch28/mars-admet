"""Module 6 explanations for the API (ADR-031): pick the explainer the routing table names, run it,
and shape the result as the `ExplainResponse` contract.

Like `prediction_service`, this only works in the built container (RDKit, XGBoost). Elsewhere
`explain_available` is False and the route answers 501, never a made-up explanation.
"""

from __future__ import annotations

from mars_contracts import (
    DescriptorAttribution,
    Endpoint,
    ExplainMethod,
    ExplainOutputSpace,
    ExplainResponse,
    FragmentAttribution,
)

from app.services import prediction_service as ps  # puts ml/ on sys.path; keep this import first

# isort: split
# The error classes have no dependencies, so the route can map them to status codes even where the
# ml stack is absent.
from serve.explain_errors import ExplainUnavailable, NothingToExplain  # noqa: E402

explain_available = False
try:
    from explain.result import ExplanationResult  # noqa: E402
    from serve.explainer import explain_endpoint  # noqa: E402

    explain_available = ps._ml_available
except ImportError:  # pragma: no cover - same environment gate as prediction_service
    pass


def _to_contract(molecule_id: str, endpoint: Endpoint, r: ExplanationResult, version: str) -> ExplainResponse:
    return ExplainResponse(
        molecule_id=molecule_id,
        endpoint=endpoint,
        method=ExplainMethod(r.method),
        model_id=r.model_id,
        output_space=ExplainOutputSpace(r.output_space),
        unit=None,
        n_seeds=r.n_seeds,
        base_value=r.base_value,
        output_value=r.output_value,
        baseline=r.baseline,
        atom_attributions=list(r.atom_attributions),
        fragment_attributions=[
            FragmentAttribution(name=f.name, smarts=f.smarts, atom_indices=list(f.atom_indices), score=f.score)
            for f in r.fragments
        ],
        whole_molecule_attributions=[
            DescriptorAttribution(name=d.name, value=d.value, score=d.score) for d in r.descriptors
        ],
        whole_molecule_rest=r.whole_molecule_rest,
        structure_total=r.structure_total,
        whole_molecule_total=r.whole_molecule_total,
        unmapped_total=r.unmapped_total,
        completeness_error=r.completeness_error,
        n_steps=r.n_steps,
        model_version=version,
    )


def explain(molecule_id: str, smiles_standardized: str, endpoint: Endpoint) -> ExplainResponse:
    """Blocking. Raises ValueError (bad molecule), NothingToExplain (stub-served), ExplainUnavailable
    (the serving model cannot answer now)."""
    registry = ps._get_registry()
    result = explain_endpoint(registry, endpoint.value, smiles_standardized, kermt=ps._get_kermt_router())
    return _to_contract(molecule_id, endpoint, result, ps.serving_version())


__all__ = ["ExplainUnavailable", "NothingToExplain", "explain", "explain_available"]
