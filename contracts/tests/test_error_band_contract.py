"""EndpointPrediction's held-out-error band fields (ADR-024) are additive: absent means no band."""

from mars_contracts import Endpoint, EndpointPrediction

BASE = dict(
    endpoint=Endpoint.SOLUBILITY,
    value=-4.2,
    confidence_low=-4.3,
    confidence_high=-4.1,
    in_domain=True,
    knn_distance=0.3,
)


def test_band_fields_default_to_none_so_existing_callers_and_cached_payloads_still_validate():
    pred = EndpointPrediction(**BASE)
    assert (pred.heldout_error_halfwidth, pred.heldout_error_level, pred.heldout_error_n) == (None, None, None)


def test_band_fields_survive_the_cache_round_trip():
    pred = EndpointPrediction(**BASE, heldout_error_halfwidth=1.677, heldout_error_level=0.9, heldout_error_n=4700)
    back = EndpointPrediction.model_validate_json(pred.model_dump_json())
    assert (back.heldout_error_halfwidth, back.heldout_error_level, back.heldout_error_n) == (1.677, 0.9, 4700)


def test_a_payload_written_before_the_fields_existed_validates():
    legacy = EndpointPrediction(**BASE).model_dump_json(exclude={"heldout_error_halfwidth", "heldout_error_level", "heldout_error_n"})
    assert EndpointPrediction.model_validate_json(legacy).heldout_error_halfwidth is None
