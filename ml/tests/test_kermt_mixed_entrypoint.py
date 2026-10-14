"""
CPU tests for the in-container glue (``train_mixed``), against a FAKE ``kermt``.

The fake is a minimal package transcribed from the real KERMT source at the
pinned tag (``task/train.py``, ``task/predict.py``, ``kermt/util/utils.py``,
``kermt/data/*``, read 2026-10-14). It proves the MARS side is wired correctly
against the *shape* of that API — paths, scaler hand-off, ``None``-vs-NaN targets,
checkpoint round trip, regression units on the way out. It cannot prove the real
KERMT behaves the same; that is what gates G1 and G2 are for.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sys
import types
from argparse import Namespace
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")
from train.kermt_mixed import train_mixed as tm  # noqa: E402

from tests.test_kermt_mixed_forward_gradnorm import _StockFinetuneTask  # noqa: E402

NAMES = ["c1", "c2", "r1"]
TYPES = ["classification", "classification", "regression"]
HEADER = ["smiles", *NAMES]


# --------------------------- fake kermt -------------------------------------


def _atoms(smiles: str) -> np.ndarray:
    n = (len(smiles) % 4) + 2
    rng = np.random.default_rng(abs(hash(smiles)) % (2**31))
    return rng.normal(size=(n, 4)).astype(np.float32)


class _Point:
    def __init__(self, line):
        self.smiles = line[0]
        self.features = None
        self.targets = [float(x) if x != "" else None for x in line[1:]]


class _Dataset(torch.utils.data.Dataset):
    def __init__(self, data):
        self.data = data

    def __len__(self):
        return len(self.data)

    def __getitem__(self, i):
        return self.data[i]

    def smiles(self):
        return [d.smiles for d in self.data]

    def targets(self):
        return [d.targets for d in self.data]

    def set_targets(self, targets):
        assert len(targets) == len(self.data)
        for d, t in zip(self.data, targets, strict=True):
            d.targets = t

    def num_tasks(self):
        return len(self.data[0].targets)

    def features_size(self):
        return 0

    def normalize_features(self, scaler=None, replace_nan_token=0):
        return object()


class _Collator:
    def __init__(self, shared_dict=None, args=None):
        self.args = args

    def __call__(self, points):
        xs, scope, start = [], [], 0
        for p in points:
            a = _atoms(p.smiles)
            xs.append(a)
            scope.append((start, len(a)))
            start += len(a)
        batch = (torch.from_numpy(np.concatenate(xs)), None, None, None, None, scope, None, None)
        t = [p.targets for p in points]
        mask = torch.tensor([[v is not None for v in row] for row in t], dtype=torch.float32)
        tgt = torch.tensor([[0.0 if v is None else v for v in row] for row in t], dtype=torch.float32)
        return [p.smiles for p in points], batch, [None] * len(points), mask, tgt


def _install_fake_kermt(monkeypatch, ckpt_path):
    def parse_args():
        argv = sys.argv[1:]
        assert argv[0] == "finetune"
        kv = {argv[i]: argv[i + 1] for i in range(1, len(argv) - 1, 2) if argv[i].startswith("--")}
        return Namespace(
            parser_name="finetune",
            data_path=kv["--data_path"],
            separate_val_path=kv["--separate_val_path"],
            separate_test_path=kv["--separate_test_path"],
            separate_val_features_path=None,
            features_path=None,
            seed=int(kv["--seed"]),
            save_dir=kv["--save_dir"],
            epochs=int(kv["--epochs"]),
            batch_size=int(kv["--batch_size"]),
            dist_coff=0.1,
            ffn_num_task_specific_layers=1,
            checkpoint_paths=[kv["--checkpoint_path"]],
            cuda=False,
            features_scaling=False,
            init_lr=1e-3,
            max_use=None,
        )

    def get_task_names(path):
        with open(path) as f:
            return next(csv.reader(f))[1:]

    def get_data(path, skip_invalid_smiles=True, args=None, features_path=None, logger=None, **kw):
        with open(path) as f:
            r = csv.reader(f)
            next(r)
            return _Dataset([_Point(line) for line in r])

    def build(args):
        return _StockFinetuneTask(args.num_tasks, False, True, 0)

    def load_checkpoint(path, current_args=None, cuda=None, logger=None, **kw):
        # kermt/util/utils.py::load_checkpoint: build from args, then merge whatever
        # parameters of matching name+shape the file has (a pretrain ckpt is partial).
        state = torch.load(path, map_location="cpu", weights_only=False)
        a = current_args or state["args"]
        model = build(a)
        merged = model.state_dict()
        for k, v in state["state_dict"].items():
            if k in merged and merged[k].shape == v.shape:
                merged[k] = v
        model.load_state_dict(merged)
        return model, state

    def build_optimizer(model, args):
        base = [p for n, p in model.named_parameters() if n.startswith("kermt")]
        ffn = [p for n, p in model.named_parameters() if not n.startswith("kermt")]
        return torch.optim.Adam([{"params": base, "lr": 1e-3}, {"params": ffn, "lr": 1e-2}])

    def save_checkpoint(path, model, scaler, features_scaler, args=None):
        state = {
            "args": args,
            "state_dict": model.state_dict(),
            "data_scaler": {"means": scaler.means, "stds": scaler.stds} if scaler is not None else None,
            "features_scaler": None,
        }
        tmp = path + ".tmp"
        torch.save(state, tmp)
        os.replace(tmp, path)

    class _Sched:
        def step(self):
            pass

    mods = {
        "kermt": types.ModuleType("kermt"),
        "kermt.data": types.ModuleType("kermt.data"),
        "kermt.data.torchvocab": types.ModuleType("kermt.data.torchvocab"),
        "kermt.util": types.ModuleType("kermt.util"),
        "kermt.util.parsing": types.ModuleType("kermt.util.parsing"),
        "kermt.util.utils": types.ModuleType("kermt.util.utils"),
    }
    mods["kermt.data"].MolCollator = _Collator
    mods["kermt.data.torchvocab"].MolVocab = object
    mods["kermt.util.parsing"].parse_args = parse_args
    u = mods["kermt.util.utils"]
    u.get_task_names = get_task_names
    u.get_data = get_data
    u.load_checkpoint = load_checkpoint
    u.build_optimizer = build_optimizer
    u.build_lr_scheduler = lambda opt, args: _Sched()
    u.save_checkpoint = save_checkpoint
    u.makedirs = lambda p, isfile=False: os.makedirs(os.path.dirname(p) if isfile else p, exist_ok=True)
    u.create_logger = lambda name, save_dir=None, quiet=False: logging.getLogger(name)
    for name, mod in mods.items():
        monkeypatch.setitem(sys.modules, name, mod)


# --------------------------- fixtures ----------------------------------------


def _write_csv(path: Path, n: int, seed: int) -> None:
    rng = np.random.default_rng(seed)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for i in range(n):
            smi = "C" * (1 + i % 9) + f"O{i}"
            c1 = "" if rng.random() < 0.1 else int(rng.random() < 0.5)
            c2 = "" if rng.random() < 0.2 else int(rng.random() < 0.5)
            r1 = "" if rng.random() < 0.7 else round(100 + 20 * rng.normal(), 3)
            w.writerow([smi, c1, c2, r1])


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    torch.manual_seed(0)
    data = tmp_path / "data"
    data.mkdir()
    _write_csv(data / "train.csv", 96, 1)
    _write_csv(data / "val.csv", 32, 2)
    ckpt = tmp_path / "pretrain.pt"
    torch.save({"args": None, "state_dict": {}}, ckpt)
    run = tmp_path / "run"
    (run / "ckpt").mkdir(parents=True)
    argv = [
        "python", "-u", "main.py", "finetune",
        "--data_path", str(data / "train.csv"),
        "--separate_val_path", str(data / "val.csv"),
        "--separate_test_path", str(data / "val.csv"),
        "--checkpoint_path", str(ckpt),
        "--epochs", "3", "--batch_size", "16", "--seed", "0",
        "--save_dir", str(run / "ckpt"),
    ]
    (run / "run.json").write_text(json.dumps({"argv": argv}))
    spec = {
        "target_names": NAMES, "task_types": TYPES,
        "loss": {"mode": "kendall"}, "min_per_task": 2,
        "hyperparameter_source": "test-fixture",
    }
    (tmp_path / "spec.json").write_text(json.dumps(spec))
    _install_fake_kermt(monkeypatch, ckpt)
    return tmp_path, run, spec


# --------------------------- pure helpers -------------------------------------


def test_finetune_argv_tail_starts_at_the_subcommand(tmp_path):
    p = tmp_path / "run.json"
    p.write_text(json.dumps({"argv": ["python", "-u", "/x/main.py", "finetune", "--seed", "3"]}))
    assert tm.finetune_argv_tail(p) == ["finetune", "--seed", "3"]
    p.write_text(json.dumps({"argv": ["python", "main.py", "predict"]}))
    with pytest.raises(ValueError, match="finetune"):
        tm.finetune_argv_tail(p)


def test_argv_value_and_spec_validation(tmp_path):
    assert tm.argv_value(["--a", "1", "--b", "2"], "--b") == "2"
    assert tm.argv_value(["--a"], "--a", "d") == "d"
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"target_names": ["a"], "task_types": ["classification", "regression"]}))
    with pytest.raises(ValueError, match="mismatch"):
        tm.load_spec(p)
    p.write_text(json.dumps({"target_names": ["a"], "task_types": ["ordinal"]}))
    with pytest.raises(ValueError, match="unknown task types"):
        tm.load_spec(p)


# --------------------------- end to end ---------------------------------------


def test_fit_writes_checkpoint_meta_and_epoch_log(workdir):
    _, run, spec = workdir
    summary = tm.run_fit(run / "run.json", spec)
    model_dir = run / "ckpt" / "fold_0" / "model_0"
    assert (model_dir / "model.pt").exists()
    meta = json.loads((model_dir / "mixed_meta.json").read_text())
    assert meta["target_names"] == NAMES and meta["loss"]["mode"] == "kendall"
    assert meta["scaler"]["is_regression"] == [False, False, True]
    assert meta["scaler"]["means"][:2] == [0.0, 0.0] and meta["scaler"]["stds"][:2] == [1.0, 1.0]
    assert 90 < meta["scaler"]["means"][2] < 110  # regression mean is in raw units

    lines = [json.loads(x) for x in (run / "logs" / "mixed_epochs.jsonl").read_text().splitlines()]
    assert lines[0]["event"] == "start" and lines[-1]["event"] == "summary"
    assert sum(1 for x in lines if x["event"] == "epoch") == 3
    assert summary["log_sigma_final"] is not None and set(summary["log_sigma_final"]) == set(NAMES)
    assert min(summary["batch_stats_epoch0"]["per_task_min"]) >= 2  # stratification applied


def test_checkpoint_stores_scaler_so_classification_is_untouched(workdir):
    _, run, spec = workdir
    tm.run_fit(run / "run.json", spec)
    state = torch.load(run / "ckpt" / "fold_0" / "model_0" / "model.pt", weights_only=False)
    means = np.asarray(state["data_scaler"]["means"])
    stds = np.asarray(state["data_scaler"]["stds"])
    assert means[0] == 0 and stds[0] == 1 and stds[2] > 1


def test_predict_returns_probabilities_for_cls_and_raw_units_for_reg(workdir, tmp_path):
    base, run, spec = workdir
    tm.run_fit(run / "run.json", spec)
    ckpt = run / "ckpt" / "fold_0" / "model_0" / "model.pt"

    pred_csv = base / "data" / "pred.csv"
    with pred_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["smiles"])
        for s in ["CCO", "CCCCN", "c1ccccc1"]:
            w.writerow([s])
    infer = base / "infer.json"
    infer.write_text(
        json.dumps({"argv": ["python", "main.py", "predict", "--data_path", str(pred_csv), "--batch_size", "2"]})
    )
    out = base / "out"
    path = tm.run_predict(infer, ckpt, out, spec)
    rows = list(csv.DictReader(path.open()))
    assert [r["smiles"] for r in rows] == ["CCO", "CCCCN", "c1ccccc1"]
    for r in rows:
        assert 0.0 < float(r["c1"]) < 1.0 and 0.0 < float(r["c2"]) < 1.0
        assert 40 < float(r["r1"]) < 160  # raw units (scaler mean ~100, std ~20), not z-scores
    assert (out / "views.csv").exists()
    header = (out / "views.csv").read_text().splitlines()[0].split(",")
    assert header[1:] == [f"{n}__atom" for n in NAMES] + [f"{n}__bond" for n in NAMES]


def test_fit_refuses_without_task_specific_heads(workdir, monkeypatch):
    _, run, spec = workdir
    import kermt.util.parsing as parsing

    real = parsing.parse_args

    def no_heads():
        a = real()
        a.ffn_num_task_specific_layers = 0
        return a

    monkeypatch.setattr(parsing, "parse_args", no_heads)
    with pytest.raises(RuntimeError, match="task_specific"):
        tm.run_fit(run / "run.json", spec)


def test_fit_refuses_mismatched_csv_targets(workdir):
    _, run, spec = workdir
    bad = dict(spec, target_names=["c1", "c2", "other"])
    with pytest.raises(RuntimeError, match="CSV targets"):
        tm.run_fit(run / "run.json", bad)


def test_main_returns_nonzero_and_json_error_on_failure(workdir, capsys):
    base, run, _ = workdir
    code = tm.main(["--mode", "predict", "--run-json", str(run / "run.json"), "--spec", str(base / "spec.json")])
    assert code == 1
    assert '"ok": false' in capsys.readouterr().out.lower()


def test_predict_accepts_a_stock_classification_checkpoint_with_no_scaler(workdir):
    """Gate G1 runs the mixed forward on a Tier-0 model, whose data_scaler is None."""
    base, run, spec = workdir
    tm.run_fit(run / "run.json", spec)
    src = run / "ckpt" / "fold_0" / "model_0" / "model.pt"
    state = torch.load(src, weights_only=False)
    state["data_scaler"] = None
    stock_like = base / "stock_like.pt"
    torch.save(state, stock_like)

    pred_csv = base / "data" / "pred2.csv"
    pred_csv.write_text("smiles\nCCO\nCCCCN\n")
    infer = base / "infer2.json"
    infer.write_text(json.dumps({"argv": ["python", "main.py", "predict", "--data_path", str(pred_csv)]}))

    # the checkpoint has 3 task heads, so request all three columns as classification:
    full_cls = {"target_names": NAMES, "task_types": ["classification"] * 3}
    out = tm.run_predict(infer, stock_like, base / "o_cls", full_cls)
    assert out.exists()
    with pytest.raises(RuntimeError, match="no data_scaler"):
        tm.run_predict(infer, stock_like, base / "o_bad", spec)  # spec has a regression column


def test_fit_requires_every_hyperparameter_to_be_supplied(workdir):
    """No silent defaults: a missing key is an error, not a quiet 0 or 2."""
    _, run, spec = workdir
    for key in ("min_per_task", "hyperparameter_source", "loss"):
        broken = {k: v for k, v in spec.items() if k != key}
        with pytest.raises(KeyError):
            tm.run_fit(run / "run.json", broken)


def test_gradnorm_arm_without_alpha_and_lr_is_refused(workdir):
    _, run, spec = workdir
    with pytest.raises(ValueError, match="gradnorm_alpha"):
        tm.run_fit(run / "run.json", dict(spec, loss={"mode": "gradnorm"}))


def test_fit_saves_every_epochs_validation_views_and_they_reproduce_predict(workdir, tmp_path):
    """The post-hoc path: views -> served units == what run_predict returns."""
    from train.kermt_mixed import posthoc
    from train.kermt_mixed.scaling import ColumnScaler

    base, run, spec = workdir
    tm.run_fit(run / "run.json", spec)
    npz = run / "logs" / "val_views.npz"
    meta = json.loads((run / "ckpt" / "fold_0" / "model_0" / "mixed_meta.json").read_text())
    assert meta["hyperparameter_source"] == "test-fixture"
    scaler = ColumnScaler.from_dict(meta["scaler"])
    flags = [t == "classification" for t in TYPES]
    preds = posthoc.epoch_predictions(npz, scaler, flags)
    assert sorted(preds) == [0, 1, 2]  # three epochs in the fixture

    best = meta["best_epoch"]
    infer = base / "infer_val.json"
    infer.write_text(
        json.dumps({"argv": ["python", "main.py", "predict", "--data_path", str(base / "data" / "val.csv")]})
    )
    out = tm.run_predict(infer, run / "ckpt" / "fold_0" / "model_0" / "model.pt", base / "o_val", spec)
    served = np.array(
        [[float(r[n]) for n in NAMES] for r in csv.DictReader(out.open())]
    )
    np.testing.assert_allclose(preds[best], served, rtol=1e-4, atol=1e-5)
