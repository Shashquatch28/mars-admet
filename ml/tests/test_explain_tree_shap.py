"""explain.tree_shap against small XGBoost models trained in the test (no dependency on promoted artifacts)."""

from __future__ import annotations

import numpy as np
import pytest
from featurize.cache import FeatureCache
from mars_contracts.endpoints import TaskType
from models.xgboost_model import XGBoostConfig, XGBoostModel
from rdkit import Chem

pytest.importorskip("xgboost", reason="xgboost not installed in this environment")
from explain.tree_shap import explain_xgboost  # noqa: E402

_TRAIN = [
    "CCO", "c1ccccc1", "CC(=O)Oc1ccccc1C(=O)O", "Cn1c(=O)c2c(ncn2C)n(c1=O)C", "OCC1OC(O)C(O)C(O)C1O",
    "CC(C)Cc1ccc(cc1)C(C)C(=O)O", "CCN(CC)CC", "c1ccc2ccccc2c1", "CC(=O)Nc1ccc(O)cc1", "OC(=O)c1ccccc1",
    "CCCCCCCC", "NCCc1ccc(O)c(O)c1", "CC(C)(C)c1ccccc1", "OC(=O)CC(O)(CC(=O)O)C(=O)O", "c1ccncc1",
    "CCOC(=O)C", "CC(=O)O", "CCCC(=O)O", "c1ccc(cc1)C(=O)N", "CCCCN", "COc1ccccc1", "CC(C)O",
    "OC(=O)C=Cc1ccccc1", "c1ccc2[nH]ccc2c1", "CCCCCC(=O)O", "ClCCl", "CC#N", "C1CCCCC1", "CCS", "O=C(O)C(N)C",
]
_ACID = Chem.MolFromSmarts("C(=O)[OH]")
_LABELS = np.array([float(Chem.MolFromSmiles(s).HasSubstructMatch(_ACID)) for s in _TRAIN])
_LOGS = np.array([-0.5 * Chem.MolFromSmiles(s).GetNumAtoms() / 3 + 0.4 * acid for s, acid in zip(_TRAIN, _LABELS, strict=True)])
_QUERY = "CC(=O)Oc1ccccc1C(=O)O"


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    return FeatureCache(tmp_path_factory.mktemp("explain_cache"))


def _train(cache, task_type, y, seeds):
    models = []
    for seed in seeds:
        cfg = XGBoostConfig(hyperparams={"n_estimators": 40, "max_depth": 3, "n_jobs": 1})
        m = XGBoostModel(task_type=task_type, cache=cache, seed=seed, xgb_config=cfg)
        m.fit(_TRAIN, y, X_val=_TRAIN, y_val=y)
        models.append(m)
    return models


class _Registry:
    def __init__(self, models):
        self._models = models

    def load_models(self, _key):
        return list(self._models)


@pytest.fixture(scope="module")
def clf_models(cache):
    return _train(cache, TaskType.CLASSIFICATION, _LABELS, seeds=(0, 1, 2))


@pytest.fixture(scope="module")
def reg_models(cache):
    return _train(cache, TaskType.REGRESSION, _LOGS, seeds=(0, 1))


def _margin(model, smiles):
    import xgboost as xgb

    feat, valid, _ = model.prepare([smiles])
    assert valid == [0]
    return float(model._model.get_booster().predict(xgb.DMatrix(feat), output_margin=True)[0])


def test_classifier_explanation_is_complete_and_in_log_odds(clf_models):
    res = explain_xgboost(_Registry(clf_models), "hia_absorption", _QUERY)
    assert res is not None
    assert res.method == "tree_shap" and res.output_space == "log_odds"
    assert res.n_seeds == 3
    expected = float(np.mean([_margin(m, _QUERY) for m in clf_models]))
    assert res.output_value == pytest.approx(expected, abs=1e-4)
    assert res.completeness_error < 1e-4
    assert res.base_value + res.structure_total + res.whole_molecule_total + res.unmapped_total == pytest.approx(
        res.output_value, abs=1e-4
    )


def test_regressor_explanation_sums_to_the_served_value(reg_models):
    res = explain_xgboost(_Registry(reg_models), "solubility_logs", _QUERY)
    assert res is not None and res.output_space == "native_unit"
    served = float(np.mean([m.predict([_QUERY])[0] for m in reg_models]))
    assert res.output_value == pytest.approx(served, abs=1e-3)
    assert res.completeness_error < 1e-3


def test_atom_scores_cover_every_atom_and_totals_are_consistent(clf_models):
    res = explain_xgboost(_Registry(clf_models), "hia_absorption", _QUERY)
    mol = Chem.MolFromSmiles(_QUERY)
    assert len(res.atom_attributions) == mol.GetNumAtoms()
    assert res.structure_total == pytest.approx(sum(res.atom_attributions))
    listed = sum(d.score for d in res.descriptors)
    assert res.whole_molecule_total == pytest.approx(listed + res.whole_molecule_rest)
    assert 0 < len(res.descriptors) <= 12
    sizes = [abs(d.score) for d in res.descriptors]
    assert sizes == sorted(sizes, reverse=True)


def test_deterministic(clf_models):
    a = explain_xgboost(_Registry(clf_models), "hia_absorption", _QUERY)
    b = explain_xgboost(_Registry(clf_models), "hia_absorption", _QUERY)
    assert a == b


def test_no_promoted_model_is_none_not_a_fabrication():
    assert explain_xgboost(_Registry([]), "hia_absorption", _QUERY) is None


def test_invalid_smiles_raises(clf_models):
    with pytest.raises(ValueError):
        explain_xgboost(_Registry(clf_models), "hia_absorption", "not a smiles (((")
