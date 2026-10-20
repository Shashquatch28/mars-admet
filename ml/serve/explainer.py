"""Which explainer answers an endpoint (ADR-031: the model that serves the value explains it).

The routing table decides, exactly as it does for `/predict`:

* routed to KERMT and the KERMT router is configured -> the service's Integrated Gradients;
* otherwise (routed to XGBoost, or KERMT serving is off, so XGBoost serves it) -> TreeSHAP on the
  promoted XGBoost seeds.

There is no fallback between the two. If KERMT is the serving model and cannot answer now, the
explanation is unavailable; it is never swapped for an explanation of a different model.
"""

from __future__ import annotations

from explain.result import ExplanationResult
from explain.tree_shap import explain_xgboost

from serve.explain_errors import ExplainUnavailable, NothingToExplain
from serve.kermt_client import KermtUnavailable


def explain_endpoint(registry, endpoint_key: str, smiles_standardized: str, *, kermt=None) -> ExplanationResult:
    if kermt is not None and endpoint_key in kermt.served_by_kermt():
        try:
            return kermt.explain(smiles_standardized, endpoint_key)
        except KermtUnavailable as exc:
            raise ExplainUnavailable(f"The KERMT service could not explain {endpoint_key}: {exc}") from exc
    result = explain_xgboost(registry, endpoint_key, smiles_standardized)
    if result is None:
        raise NothingToExplain(f"No promoted model serves {endpoint_key}; it is stub-served, so there is nothing to explain.")
    return result
