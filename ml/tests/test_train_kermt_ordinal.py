"""Host-side tests for the Tier-2 ordinal driver (model replaced by a TEST DOUBLE)."""

from __future__ import annotations

import json
import zlib
from pathlib import Path

import numpy as np
import pytest
from configs.experiment_config import ExperimentConfig
from data.cluster_loaders import load_cluster
from mars_contracts.endpoints import TaskType
from train import train_kermt_ordinal as t2

from tests.test_train_kermt_cluster_calibration import _mols, _write

KEYS = ["herg_cardiotoxicity", "ames_mutagenicity", "clearance_microsomal"]
TT = {
    "herg_cardiotoxicity": TaskType.CLASSIFICATION,
    "ames_mutagenicity": TaskType.CLASSIFICATION,
    "clearance_microsomal": TaskType.REGRESSION,
}


@pytest.fixture
def prep(tmp_path) -> Path:
    root = tmp_path / "20261014T000001Z"
    layout = {
        "herg_cardiotoxicity": dict(test=[0, 1], tv=range(2, 20), cal=[18, 19], mod=2),
        "ames_mutagenicity": dict(test=[1, 2], tv=[0, *range(3, 20)], cal=[17, 18], mod=3),
        "clearance_microsomal": dict(test=[0, 1], tv=range(3, 20), cal=[18, 19], mod=None),
    }
    for key, s in layout.items():
        ds = root / key
        ds.mkdir(parents=True)
        tv, te, ca = _mols(s["tv"]), _mols(s["test"]), _mols(s["cal"])
        if s["mod"] is None:
            lab = lambda n: [1.0 + 0.37 * i for i in range(n)]  # noqa: E731
            cal_lab = lab
        else:
            lab = lambda n, m=s["mod"]: [float(i % m == 0) for i in range(n)]  # noqa: E731
            cal_lab = lambda n: [float(i % 2 == 0) for i in range(n)]  # noqa: E731
        _write(ds, "train_val", tv, lab(len(tv)))
        _write(ds, "test", te, lab(len(te)))
        _write(ds, "calibration", ca, cal_lab(len(ca)))
        (ds / "provenance.json").write_text(json.dumps({"split_method": "adopt_benchmark"}))
    return root


class FakeKermt:
    """TEST DOUBLE: records fit labels; predicts deterministic probabilities."""

    instances: list[FakeKermt] = []

    def __init__(self, wide_names, checkpoint, seed, kermt_config):
        self.names = list(wide_names)
        self.model_id = "stub-not-kermt"
        FakeKermt.instances.append(self)

    def fit(self, X_train, y_train, *, X_val=None, y_val=None, run_dir=None):
        self.fit_args = (list(X_train), np.asarray(y_train), list(X_val), np.asarray(y_val))

    def predict(self, X, run_dir=None):
        out = np.zeros((len(X), len(self.names)))
        for i, s in enumerate(X):
            u = (zlib.crc32(s.encode()) % 1000) / 1000.0
            for j, n in enumerate(self.names):
                out[i, j] = max(0.0, min(1.0, 1.0 - u - 0.05 * j)) if "__gt" in n else 0.2 + 0.6 * u
        return out

    def save(self, path):
        Path(path).mkdir(parents=True, exist_ok=True)


@pytest.fixture(autouse=True)
def _reset():
    FakeKermt.instances = []


def _cd(prep):
    return load_cluster(prep, KEYS, cluster_key="mixed")


def _run(prep, tmp_path, **kw):
    cd = _cd(prep)
    cfg = ExperimentConfig("mixed", "kermt_ordinal", 0, cd.prep_id)
    kw.setdefault("n_bins", 4)
    kw.setdefault("strategy", "quantile")
    kw.setdefault("hyperparameter_source", "test-fixture")
    return cd, t2.train_one_seed_ordinal(
        cd, cfg, 0, checkpoint=Path("s.pt"), runs_dir=tmp_path / "runs",
        model_factory=lambda names, ck, seed, kc: FakeKermt(names, ck, seed, kc), **kw,
    )


# ---- encoding ----------------------------------------------------------------


def test_wide_layout_expands_only_regression_endpoints():
    y = np.array([[1, 0, 1.0], [0, 1, 5.0], [1, 1, 9.0], [0, 0, 3.0]])
    codecs = t2.fit_codecs(y, KEYS, TT, n_bins=3, strategy="quantile")
    assert set(codecs) == {"clearance_microsomal"}
    lay = t2.wide_layout(KEYS, TT, codecs)
    assert lay.names[:2] == ("herg_cardiotoxicity", "ames_mutagenicity")
    assert all(n.startswith("clearance_microsomal__gt") for n in lay.names[2:])
    assert lay.n_columns == 2 + codecs["clearance_microsomal"].n_thresholds


def test_encode_decode_roundtrip_is_exact_when_the_model_is_perfect():
    rng = np.random.default_rng(0)
    y = np.column_stack([(rng.random(300) < 0.5), (rng.random(300) < 0.4), rng.normal(10, 3, 300)]).astype(float)
    y[::9, 0] = np.nan
    codecs = t2.fit_codecs(y, KEYS, TT, n_bins=8, strategy="quantile")
    lay = t2.wide_layout(KEYS, TT, codecs)
    wide = t2.encode_wide(y, lay, TT, codecs)
    assert np.isnan(wide[::9, 0]).all()  # missing label stays missing (masked, not 0)
    dec = t2.decode_wide(np.nan_to_num(wide), lay, TT, codecs)
    np.testing.assert_allclose(dec[:, 1], y[:, 1])  # classification passes through
    ceiling = np.mean(np.abs(dec[:, 2] - y[:, 2]))
    assert ceiling == pytest.approx(
        t2.discretization_ceiling_mae(codecs["clearance_microsomal"], y[:, 2])
    )


def test_calibration_scores_are_logits_for_classification_and_raw_for_regression():
    y = np.column_stack([np.zeros(6), np.ones(6), np.linspace(1, 6, 6)])
    codecs = t2.fit_codecs(y, KEYS, TT, n_bins=3, strategy="quantile")
    lay = t2.wide_layout(KEYS, TT, codecs)
    p = np.full((4, lay.n_columns), 0.5)
    dec = t2.decode_wide(p, lay, TT, codecs)
    sc = t2.scores_for_calibration(p, dec, lay, TT)
    assert sc[:, 0] == pytest.approx(0.0) and sc[:, 1] == pytest.approx(0.0)  # logit(0.5)
    np.testing.assert_array_equal(sc[:, 2], dec[:, 2])


# ---- the run -------------------------------------------------------------------


def test_run_trains_all_classification_and_reports_decoded_regression(prep, tmp_path):
    cd, res = _run(prep, tmp_path)
    model = FakeKermt.instances[0]
    assert all(n in model.names for n in ("herg_cardiotoxicity", "ames_mutagenicity"))
    assert sum("__gt" in n for n in model.names) >= 2
    assert model.fit_args[1].shape[1] == len(model.names)
    assert type(res.per_endpoint_metrics["clearance_microsomal"]).__name__ == "RegressionMetrics"
    assert res.calibration["clearance_microsomal"]["status"] == "skipped_regression"
    assert res.calibration["herg_cardiotoxicity"]["status"] in ("fitted", "fitted_at_boundary")
    assert res.run_id.startswith("kermt_ord_mixed_seed0_bins4_")


def test_codec_is_fit_on_the_train_fold_only(prep, tmp_path):
    cd, res = _run(prep, tmp_path)
    run_dir = Path(res.model_path).parents[1]
    codecs = json.loads((run_dir / "ordinal" / "codecs.json").read_text())
    thr = codecs["clearance_microsomal"]["thresholds"]
    model = FakeKermt.instances[0]
    train_smiles, y_train = model.fit_args[0], model.fit_args[1]
    assert len(train_smiles) == len(y_train)
    test = cd.endpoint_test_frame("clearance_microsomal")
    # thresholds are quantiles of TRAIN labels: they are not the test set's quantiles
    q = np.quantile(test["clearance_microsomal"].to_numpy(), [0.25, 0.5, 0.75])
    assert not np.allclose(sorted(thr), q)


def test_guards_and_required_provenance(prep, tmp_path):
    cd = _cd(prep)
    base = dict(checkpoint=Path("s.pt"), runs_dir=tmp_path / "r", n_bins=4, strategy="quantile",
                hyperparameter_source="t", model_factory=lambda *a: FakeKermt(*a))
    with pytest.raises(ValueError, match="kermt_ordinal"):
        t2.train_one_seed_ordinal(cd, ExperimentConfig("m", "kermt_mixed", 0, cd.prep_id), 0, **base)
    cfg = ExperimentConfig("m", "kermt_ordinal", 0, cd.prep_id)
    with pytest.raises(ValueError, match="hyperparameter_source"):
        t2.train_one_seed_ordinal(cd, cfg, 0, **{**base, "hyperparameter_source": ""})
    with pytest.raises(TypeError):  # n_bins has no default
        t2.train_one_seed_ordinal(
            cd, cfg, 0, checkpoint=Path("s.pt"), strategy="quantile", hyperparameter_source="t"
        )  # type: ignore[call-arg]


# ---- the gate --------------------------------------------------------------------


def test_t2_gate_requires_tolerance_and_aggregation_to_be_stated():
    dec = {"a": [1.10, 1.18], "b": [1.0, 1.0]}
    direct = {"a": [1.0, 1.0], "b": [1.0, 1.0]}
    with pytest.raises(TypeError):
        t2.t2_decoded_mae_gate(dec, direct)  # type: ignore[call-arg]
    strict = t2.t2_decoded_mae_gate(dec, direct, rel_tol=0.15, aggregation="all_pairs")
    assert not strict.passed  # the 1.18 pair exceeds 1.15
    lenient = t2.t2_decoded_mae_gate(dec, direct, rel_tol=0.15, aggregation="mean_per_endpoint")
    assert lenient.passed  # mean 1.14 <= 1.15: the aggregation rule changes the verdict
