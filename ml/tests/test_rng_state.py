"""
Tests for utils/rng_state.py.

CPU-only. torch and CUDA are reached through ``FakeTorch`` so every branch (CPU RNG,
CUDA RNG, device-count mismatch, torch absent) runs without a GPU or torch installed.
"""

from __future__ import annotations

import builtins
import random
import sys

import numpy as np
import pytest
from utils.rng_state import (
    RNG_STATE_VERSION,
    RngState,
    RngStateError,
    capture_rng_state,
    load_rng_state,
    restore_rng_state,
    save_rng_state,
)


class FakeTensor:
    def __init__(self, data):
        self._d = [int(x) for x in data]

    def tolist(self):
        return list(self._d)


class FakeCuda:
    def __init__(self, n: int):
        self.n = n
        self.states = [FakeTensor([i + 1] * 8) for i in range(n)]

    def is_available(self):
        return self.n > 0

    def device_count(self):
        return self.n

    def get_rng_state_all(self):
        return [FakeTensor(t.tolist()) for t in self.states]

    def set_rng_state_all(self, lst):
        self.states = [FakeTensor(t.tolist()) for t in lst]


class FakeTorch:
    __version__ = "fake-1.0"
    uint8 = "uint8"

    def __init__(self, cuda: int = 0):
        self._cpu = FakeTensor(range(16))
        self.cuda = FakeCuda(cuda)

    def get_rng_state(self):
        return FakeTensor(self._cpu.tolist())

    def set_rng_state(self, t):
        self._cpu = FakeTensor(t.tolist())

    def tensor(self, data, dtype=None):
        assert dtype == "uint8"
        return FakeTensor(data)

    def scramble(self):
        self._cpu = FakeTensor(x + 7 for x in self._cpu.tolist())


# ---------------------------------------------------------------------------- #
# Python + NumPy
# ---------------------------------------------------------------------------- #


def test_python_rng_roundtrip_reproduces_the_continuation():
    random.seed(123)
    state = capture_rng_state(include_torch=False)
    expected = [random.random() for _ in range(5)]

    random.seed(999)  # scramble
    restore_rng_state(state)
    assert [random.random() for _ in range(5)] == expected


def test_numpy_global_rng_roundtrip_reproduces_the_continuation():
    np.random.seed(7)
    state = capture_rng_state(include_torch=False)
    expected = np.random.rand(6)

    np.random.seed(0)
    restore_rng_state(state)
    np.testing.assert_array_equal(np.random.rand(6), expected)


def test_numpy_gauss_cache_is_part_of_the_state():
    """np.random.normal caches a second Box-Muller value; losing it desyncs the stream."""
    np.random.seed(11)
    np.random.randn()  # leaves a cached gaussian behind
    state = capture_rng_state(include_torch=False)
    assert state.numpy["has_gauss"] in (0, 1)
    expected = np.random.randn(4)

    np.random.seed(0)
    restore_rng_state(state)
    np.testing.assert_array_equal(np.random.randn(4), expected)


def test_named_numpy_generator_roundtrip():
    gen = np.random.default_rng(5)
    gen.random(3)
    state = capture_rng_state(numpy_generators={"sampler": gen}, include_torch=False)
    expected = gen.random(4)

    gen2 = np.random.default_rng(999)
    restore_rng_state(state, numpy_generators={"sampler": gen2})
    np.testing.assert_array_equal(gen2.random(4), expected)


def test_missing_named_generator_is_an_error_in_strict_mode():
    gen = np.random.default_rng(1)
    state = capture_rng_state(numpy_generators={"sampler": gen}, include_torch=False)
    with pytest.raises(RngStateError, match="Generator 'sampler'"):
        restore_rng_state(state)


def test_capture_does_not_advance_any_generator():
    random.seed(3)
    np.random.seed(3)
    before_py, before_np = random.getstate(), np.random.get_state()
    capture_rng_state(include_torch=False)
    capture_rng_state(include_torch=False)
    assert random.getstate() == before_py
    after = np.random.get_state()
    assert after[0] == before_np[0] and after[2:] == before_np[2:]
    np.testing.assert_array_equal(after[1], before_np[1])


# ---------------------------------------------------------------------------- #
# Deterministic serialization + versioning
# ---------------------------------------------------------------------------- #


def test_serialization_is_deterministic_and_digest_stable():
    random.seed(1)
    np.random.seed(1)
    a = capture_rng_state(include_torch=False)
    b = capture_rng_state(include_torch=False)
    assert a.to_json() == b.to_json()
    assert a.digest() == b.digest()


def test_state_change_changes_the_digest():
    random.seed(1)
    a = capture_rng_state(include_torch=False)
    random.random()
    b = capture_rng_state(include_torch=False)
    assert a.digest() != b.digest()


def test_json_is_compact_sorted_and_ascii():
    s = capture_rng_state(include_torch=False).to_json()
    assert s.isascii()
    assert ", " not in s and ": " not in s
    assert s.index('"env"') < s.index('"numpy"') < s.index('"python"') < s.index('"version"')


def test_json_roundtrip_and_file_roundtrip(tmp_path):
    random.seed(9)
    np.random.seed(9)
    state = capture_rng_state(include_torch=False)
    assert RngState.from_json(state.to_json()) == state

    path = save_rng_state(state, tmp_path / "ckpt" / "rng.json")
    assert load_rng_state(path) == state
    assert path.read_text(encoding="utf-8") == state.to_json() + "\n"  # same state, same bytes


def test_version_is_recorded_and_checked():
    state = capture_rng_state(include_torch=False)
    assert state.version == RNG_STATE_VERSION == "mars-rng-state-v1"

    stale = RngState.from_dict({**state.to_dict(), "version": "mars-rng-state-v0"})
    with pytest.raises(RngStateError, match="unsupported RNG state version"):
        restore_rng_state(stale)


def test_pythonhashseed_is_recorded_but_not_claimed_restorable(monkeypatch):
    monkeypatch.setenv("PYTHONHASHSEED", "42")
    assert capture_rng_state(include_torch=False).env == {"PYTHONHASHSEED": "42"}


# ---------------------------------------------------------------------------- #
# torch CPU / CUDA (fake) - no GPU, no torch required
# ---------------------------------------------------------------------------- #


def test_torch_cpu_state_roundtrip():
    torch = FakeTorch()
    state = capture_rng_state(torch_module=torch)
    assert state.torch_cpu is not None and state.torch_version == "fake-1.0"
    original = torch.get_rng_state().tolist()

    torch.scramble()
    assert torch.get_rng_state().tolist() != original
    restore_rng_state(state, torch_module=torch)
    assert torch.get_rng_state().tolist() == original


def test_cuda_state_roundtrip_across_devices():
    torch = FakeTorch(cuda=2)
    state = capture_rng_state(torch_module=torch)
    assert state.torch_cuda is not None and len(state.torch_cuda) == 2
    original = [t.tolist() for t in torch.cuda.get_rng_state_all()]

    torch.cuda.states = [FakeTensor([99] * 8), FakeTensor([98] * 8)]
    restore_rng_state(state, torch_module=torch)
    assert [t.tolist() for t in torch.cuda.get_rng_state_all()] == original


def test_cuda_absent_means_no_cuda_state_captured():
    state = capture_rng_state(torch_module=FakeTorch(cuda=0))
    assert state.torch_cpu is not None
    assert state.torch_cuda is None


def test_cuda_device_count_mismatch_is_refused_in_strict_mode():
    state = capture_rng_state(torch_module=FakeTorch(cuda=2))
    with pytest.raises(RngStateError, match="2 CUDA RNG states but 1 device"):
        restore_rng_state(state, torch_module=FakeTorch(cuda=1))


def test_cuda_missing_at_restore_time_is_refused_in_strict_mode():
    state = capture_rng_state(torch_module=FakeTorch(cuda=1))
    with pytest.raises(RngStateError, match="CUDA is not available"):
        restore_rng_state(state, torch_module=FakeTorch(cuda=0))


def test_non_strict_restore_warns_and_restores_what_it_can():
    torch_src = FakeTorch(cuda=2)
    random.seed(21)
    state = capture_rng_state(torch_module=torch_src)
    expected = random.random()

    random.seed(0)
    dest = FakeTorch(cuda=1)
    with pytest.warns(RuntimeWarning, match="device"):
        restore_rng_state(state, torch_module=dest, strict=False)
    assert random.random() == expected  # python restored
    assert dest.get_rng_state().tolist() == torch_src.get_rng_state().tolist()  # cpu restored


def test_strict_failure_happens_before_any_state_is_touched():
    """All-or-nothing: a refused restore must not have half-applied."""
    state = capture_rng_state(torch_module=FakeTorch(cuda=2))
    random.seed(1234)
    marker = random.getstate()
    with pytest.raises(RngStateError):
        restore_rng_state(state, torch_module=FakeTorch(cuda=1))
    assert random.getstate() == marker


# ---------------------------------------------------------------------------- #
# torch absent
# ---------------------------------------------------------------------------- #


def test_capture_works_when_torch_is_not_importable(monkeypatch):
    real_import = builtins.__import__

    def _no_torch(name, *a, **k):
        if name == "torch" or name.startswith("torch."):
            raise ImportError("torch blocked for this test")
        return real_import(name, *a, **k)

    monkeypatch.delitem(sys.modules, "torch", raising=False)
    monkeypatch.setattr(builtins, "__import__", _no_torch)
    state = capture_rng_state()
    assert state.torch_cpu is None and state.torch_cuda is None and state.torch_version is None
    assert state.python and state.numpy  # the rest still captured


def test_restoring_a_torch_state_without_torch_is_refused_in_strict_mode(monkeypatch):
    state = capture_rng_state(torch_module=FakeTorch())
    real_import = builtins.__import__

    def _no_torch(name, *a, **k):
        if name == "torch":
            raise ImportError("blocked")
        return real_import(name, *a, **k)

    monkeypatch.delitem(sys.modules, "torch", raising=False)
    monkeypatch.setattr(builtins, "__import__", _no_torch)
    with pytest.raises(RngStateError, match="torch is not importable"):
        restore_rng_state(state)


def test_include_torch_false_skips_torch_even_when_available():
    state = capture_rng_state(torch_module=FakeTorch(cuda=1), include_torch=False)
    assert state.torch_cpu is None and state.torch_cuda is None


def test_real_torch_roundtrip_when_installed():
    torch = pytest.importorskip("torch")
    torch.manual_seed(5)
    state = capture_rng_state()
    expected = torch.rand(4)
    torch.manual_seed(0)
    restore_rng_state(state)
    assert torch.equal(torch.rand(4), expected)


def test_module_is_self_contained():
    """It must be stageable into the KERMT container: stdlib only at import time.

    numpy and torch are imported lazily through ``importlib`` (inside functions), so
    no MARS package - and no third-party package - appears among the static imports.
    """
    import ast

    import utils.rng_state as m

    tree = ast.parse(open(m.__file__, encoding="utf-8").read())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])

    assert imported <= set(sys.stdlib_module_names), imported - set(sys.stdlib_module_names)
