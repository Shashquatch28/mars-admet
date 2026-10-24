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
from serve.explain_errors import (  # noqa: E402
    ExplainBusy,
    ExplainJobLost,
    ExplainUnavailable,
    NothingToExplain,
)

explain_available = False
try:
    from explain.result import ExplanationResult  # noqa: E402
    from serve.explainer import explain_endpoint  # noqa: E402
    from serve.kermt_client import (  # noqa: E402
        JobSnapshot,
        KermtBusy,
        KermtJobNotFound,
        KermtUnavailable,
    )

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
        converged=r.converged,
        seed_agreement=r.seed_agreement,
        n_steps=r.n_steps,
        model_version=version,
    )


def explain(molecule_id: str, smiles_standardized: str, endpoint: Endpoint) -> ExplainResponse:
    """Blocking. Raises ValueError (bad molecule), NothingToExplain (stub-served), ExplainUnavailable
    (the serving model cannot answer now)."""
    registry = ps._get_registry()
    result = explain_endpoint(registry, endpoint.value, smiles_standardized, kermt=ps._get_kermt_router())
    return _to_contract(molecule_id, endpoint, result, ps.serving_version())


# ---- KERMT-served explanations are background jobs in the service (ADR-040). All blocking: run them on the pool. ----


def kermt_serves(endpoint: Endpoint) -> bool:
    """True when the routing sends this endpoint to KERMT and KERMT serving is on, so its explanation is a job."""
    if not explain_available:
        return False
    router = ps._get_kermt_router()
    return router is not None and endpoint.value in router.served_by_kermt()


def _kermt_call(fn, *args):
    router = ps._get_kermt_router()
    try:
        return fn(router, *args)
    except KermtBusy as exc:
        raise ExplainBusy(str(exc)) from exc
    except KermtJobNotFound as exc:
        raise ExplainJobLost(str(exc)) from exc
    except KermtUnavailable as exc:
        raise ExplainUnavailable(f"The KERMT service could not answer: {exc}") from exc


def kermt_digest() -> str:
    """Digest of the IG parameters and loaded seeds; part of the cache key so a changed baseline never serves a stale result."""
    return _kermt_call(lambda router: router.explain_params_digest())


def kermt_submit(smiles_standardized: str, endpoint: Endpoint) -> JobSnapshot:
    return _kermt_call(lambda router: router.submit_explain_job(smiles_standardized, endpoint.value))


def kermt_status(job_id: str) -> JobSnapshot:
    return _kermt_call(lambda router: router.explain_job(job_id))


def kermt_cancel(job_id: str) -> JobSnapshot:
    return _kermt_call(lambda router: router.cancel_explain_job(job_id))


def kermt_finish(molecule_id: str, smiles_standardized: str, endpoint: Endpoint, snap: JobSnapshot) -> ExplainResponse:
    """A finished job -> the contract response (fragments and totals are derived here, once)."""
    router = ps._get_kermt_router()
    if snap.result is None:
        raise ExplainUnavailable("The service reported the job done without a result")
    try:
        result = router.assemble_raw(smiles_standardized, endpoint.value, snap.result)
    except KermtUnavailable as exc:
        raise ExplainUnavailable(f"The KERMT service returned an unusable explanation: {exc}") from exc
    return _to_contract(molecule_id, endpoint, result, ps.serving_version())


__all__ = [
    "ExplainBusy",
    "ExplainJobLost",
    "ExplainUnavailable",
    "NothingToExplain",
    "explain",
    "explain_available",
    "kermt_cancel",
    "kermt_digest",
    "kermt_finish",
    "kermt_serves",
    "kermt_status",
    "kermt_submit",
]
