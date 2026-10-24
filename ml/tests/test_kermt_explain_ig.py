"""Integrated Gradients on KERMT's real model class, with RANDOM weights (ADR-031).

This proves the machinery: that the differentiable forward is KERMT's own forward, that attributions are
complete (sum to f(x) - f(baseline)), that atoms line up with RDKit's atom order, and that the engine lock is
released between chunks. It says nothing about real checkpoints (a random model's output barely moves), so
it does not replace running `explain` against the real Tier-0 checkpoints in the KERMT image.

Skipped unless torch and the KERMT source are importable. KERMT is third-party code that cannot be imported
into the project environments (it imports cuik_molmaker unconditionally); point KERMT_SRC at a checkout of
NVIDIA-BioNeMo/KERMT at e402473. Where cuik_molmaker / descriptastorus are missing, empty stand-ins are
installed: this test never calls them.
"""

from __future__ import annotations

import os
import sys
import threading
import types
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="torch not installed in this environment")

KERMT_SRC = Path(os.environ.get("KERMT_SRC", Path(__file__).resolve().parents[3] / "kermt-src"))
if not (KERMT_SRC / "kermt").is_dir():
    pytest.skip(f"KERMT source not found at {KERMT_SRC} (set KERMT_SRC)", allow_module_level=True)

SERVICE_DIR = Path(__file__).resolve().parents[1] / "serve" / "kermt_service"


def _stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__path__ = []  # behave as a package

    def _getattr(attr: str):
        if attr.startswith("__"):
            raise AttributeError(attr)
        return lambda *a, **k: None

    mod.__getattr__ = _getattr  # type: ignore[method-assign]
    sys.modules[name] = mod
    return mod


for _name in ("cuik_molmaker", "cuik_molmaker.mol_features", "descriptastorus", "descriptastorus.descriptors"):
    try:
        __import__(_name)
    except ImportError:
        _stub(_name)
for _parent, _child in (("cuik_molmaker", "mol_features"), ("descriptastorus", "descriptors")):
    if not hasattr(sys.modules[_parent], _child):
        setattr(sys.modules[_parent], _child, sys.modules[f"{_parent}.{_child}"])
for _p in (str(KERMT_SRC), str(SERVICE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import explain_ig as ig  # noqa: E402
from kermt.data.molgraph import mol2graph  # noqa: E402
from kermt.model.models import KermtFinetuneTask  # noqa: E402
from kermt.util.parsing import get_newest_train_args  # noqa: E402
from rdkit import Chem  # noqa: E402

D = 24  # descriptor width of the toy model
SMILES = "CC(=O)Oc1ccccc1C(=O)O"


class _LM:
    pass


@pytest.fixture(scope="module")
def lm():
    torch.manual_seed(0)
    args = get_newest_train_args()
    for k, v in dict(
        hidden_size=48, num_mt_block=1, num_attn_head=2, embedding_output_type="both", self_attention=False,
        ffn_num_layers=2, ffn_hidden_size=48, features_only=False, features_size=D, dataset_type="classification",
        ffn_num_task_specific_layers=1, ffn_task_specific_hidden_size=24, num_tasks=2, output_size=1,
        backbone="gtrans", bias=False, activation="ReLU", dropout=0.0, cuda=False,
        use_cuikmolmaker_featurization=False, no_cache=False, bond_drop_rate=0.0, attn_hidden=16, attn_out=2,
    ).items():
        setattr(args, k, v)
    model = KermtFinetuneTask(args)
    model.eval()
    out = _LM()
    out.model, out.args, out.scaler, out.task_type = model, args, None, "classification"
    return out


@pytest.fixture(scope="module")
def descriptors():
    return np.random.default_rng(0).uniform(0, 1, size=D)


def _attribute(lm, descriptors, target=0, lock=None, **kw):
    kw.setdefault("schedule", (128,))
    kw.setdefault("chunk", 32)
    return ig.attribute_checkpoint(
        lm, SMILES, descriptors, target, shared_dict={}, lock=lock or threading.Lock(), rel_tol=0.0, abs_tol=0.0, **kw
    )


def test_the_differentiable_forward_is_kermts_own_forward(lm, descriptors):
    comps = mol2graph([SMILES], {}, lm.args).get_components()
    with torch.no_grad():
        stock = lm.model(comps, [descriptors]).numpy()[0]
    for target in (0, 1):
        assert _attribute(lm, descriptors, target).f_x == pytest.approx(stock[target], abs=1e-5)


def test_attributions_are_complete_and_one_per_atom(lm, descriptors):
    n = Chem.MolFromSmiles(SMILES).GetNumAtoms()
    for target in (0, 1):
        sa = _attribute(lm, descriptors, target, schedule=(256,))
        assert sa.atom_scores.shape == (n,) and sa.descriptor_scores.shape == (D,)
        total = sa.atom_scores.sum() + sa.descriptor_scores.sum()
        delta = sa.f_x - sa.f_baseline
        assert abs(total - delta) <= 0.1 * abs(delta) + 2e-3


def test_the_engine_lock_is_released_between_chunks(lm, descriptors):
    class Counting:
        def __init__(self):
            self.held = 0
            self.entered = 0

        def __enter__(self):
            self.entered += 1
            self.held += 1
            assert self.held == 1  # never re-entered while held

        def __exit__(self, *a):
            self.held -= 1

    lock = Counting()
    _attribute(lm, descriptors, 0, lock=lock, schedule=(64,), chunk=16)
    assert lock.held == 0
    assert lock.entered >= 64 // 16  # taken once per chunk (plus the two endpoint evaluations), not once overall


def test_a_molecule_with_no_bonds_is_explained(lm, descriptors):
    """Methane has one heavy atom and no bonds; the bond tensor has no rows, which broke a reshape(-1)."""
    sa = ig.attribute_checkpoint(
        lm, "C", descriptors, 0, shared_dict={}, lock=threading.Lock(), schedule=(32,), chunk=8, rel_tol=0.0, abs_tol=0.0
    )
    assert sa.atom_scores.shape == (1,) and np.isfinite(sa.atom_scores).all()
    assert np.isfinite(sa.descriptor_scores).all()


def test_a_non_finite_descriptor_vector_is_refused_not_crashed_on(lm, descriptors):
    """Selenium makes the descriptor generator return NaN; that used to surface as a 500 from a JSON encode error."""
    bad = descriptors.copy()
    bad[3] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        ig.attribute_checkpoint(lm, SMILES, bad, 0, shared_dict={}, lock=threading.Lock(), schedule=(32,))


def test_attributions_are_finite_for_another_descriptor_vector(lm):
    base = np.random.default_rng(1).uniform(0, 1, size=D)
    a = _attribute(lm, base, 0, schedule=(64,))
    assert np.isfinite(a.atom_scores).all() and np.isfinite(a.descriptor_scores).all()


class _FakeNormalized:
    def __init__(self, columns):
        self.columns = columns


def _with_columns(monkeypatch, columns):
    fake = types.SimpleNamespace(RDKit2DNormalized=lambda: _FakeNormalized(columns))
    monkeypatch.setattr(sys.modules["descriptastorus.descriptors"], "rdNormalizedDescriptors", fake, raising=False)


def test_descriptor_names_match_the_vector_the_model_reads(monkeypatch):
    """`.columns` holds exactly the descriptor names (200 in the pinned image); `process()` has a leading flag that
    the feature generator drops. Stripping a column that is not there made the names 199 long and every name generic."""
    names = [f"desc{i}" for i in range(200)]
    _with_columns(monkeypatch, [(n, float) for n in names])
    assert ig.descriptor_names(200) == names
    _with_columns(monkeypatch, [("RDKit2D_calculated", bool), *[(n, float) for n in names]])  # older versions list the flag
    assert ig.descriptor_names(200) == names
    _with_columns(monkeypatch, [(n, float) for n in names[:150]])  # cannot be matched: say so with generic names
    assert ig.descriptor_names(200)[0] == "rdkit2d_feature_0"


def test_stage_is_reported_per_run_and_a_cancel_stops_between_chunks(lm, descriptors):
    from explain.graph_ig import IGCancelled

    stages: list[int] = []
    _attribute(lm, descriptors, 0, schedule=(64, 128), chunk=16, on_stage=stages.append)
    assert stages == [64, 128]  # rel_tol=0 never converges, so both steps are run, in order

    calls = []

    def cancel_after_two_chunks():
        calls.append(1)
        return len(calls) > 2

    lock = threading.Lock()
    with pytest.raises(IGCancelled):
        _attribute(lm, descriptors, 0, lock=lock, schedule=(64,), chunk=16, should_cancel=cancel_after_two_chunks)
    assert len(calls) == 3 and not lock.locked()  # stopped at the third check, lock not left held
