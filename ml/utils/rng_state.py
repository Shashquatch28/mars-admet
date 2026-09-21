"""
RNG-state capture and restore, for checkpoint/resume.

Blueprint Module 10 makes this mandatory: a checkpoint must carry the Python, NumPy
and PyTorch RNG state, otherwise a run resumed after a preemption silently diverges
from what "seed N" means. Until now MARS recorded only the integer seed
(``utils.seed.set_global_seed``); nothing captured or restored generator state.

Design constraints
------------------
* **Self-contained**: stdlib + optional numpy + optional torch. No MARS imports, so
  this file can be staged into the KERMT container next to a trainer.
* **CPU-testable**: torch and CUDA are reached through an injectable ``torch_module``,
  so the unit tests exercise every branch with a fake and need no GPU (or torch).
* **Deterministic serialization**: compact JSON with sorted keys and fixed separators;
  the same state always yields the same bytes and the same digest.
* **Versioned**: ``RNG_STATE_VERSION`` is written into every state and checked on
  restore.
* **Observation-free**: capturing never advances any generator.

What is captured
----------------
Python ``random``; NumPy's legacy global ``RandomState`` (what ``np.random.seed``
seeds, and what ``set_global_seed`` uses); optionally named NumPy ``Generator``s;
PyTorch CPU RNG when torch is importable; the CUDA RNG of every visible device when
CUDA is available.

What is NOT captured (and cannot be, in-process)
------------------------------------------------
``PYTHONHASHSEED`` is fixed at interpreter start; it is recorded in ``env`` for
provenance but cannot be restored. cuDNN/CUDA kernel non-determinism is not RNG state
at all - bit-exact resumption of a GPU run additionally needs deterministic
algorithms, which KERMT's own determinism has NOT been established for.

Future KERMT integration points (deliberately not wired yet)
-----------------------------------------------------------
1. The stock path (``KermtModel`` -> ``run_finetune_local.py`` in the container)
   owns its own training loop; MARS cannot checkpoint inside it. At most, capture the
   HOST RNG in ``train.train_kermt_cluster.train_one_seed`` right after
   ``set_global_seed(seed)`` and store it beside the run's artifacts.
2. The real integration point is the Tier-1 trainer's epoch loop
   (``ml/train/kermt_mixed/train_mixed.py``, which runs INSIDE the container): call
   ``save_rng_state`` next to each model/optimizer/scheduler checkpoint and
   ``restore_rng_state`` on resume. Stage this file with that trainer.
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import random
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RNG_STATE_VERSION = "mars-rng-state-v1"


class RngStateError(RuntimeError):
    """A saved RNG state cannot be restored in the current environment."""


def _import_optional(name: str) -> Any | None:
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _tensor_to_b64(tensor: Any) -> str:
    return _b64(bytes(int(x) for x in tensor.tolist()))


def _b64_to_tensor(torch: Any, text: str) -> Any:
    return torch.tensor(list(base64.b64decode(text)), dtype=torch.uint8)


@dataclass(frozen=True)
class RngState:
    """A snapshot of every RNG MARS cares about. Immutable and JSON-serializable."""

    version: str
    python: dict[str, Any]
    numpy: dict[str, Any] | None
    numpy_generators: dict[str, Any] = field(default_factory=dict)
    torch_cpu: str | None = None
    torch_cuda: list[str] | None = None
    torch_version: str | None = None
    env: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "python": self.python,
            "numpy": self.numpy,
            "numpy_generators": self.numpy_generators,
            "torch_cpu": self.torch_cpu,
            "torch_cuda": self.torch_cuda,
            "torch_version": self.torch_version,
            "env": self.env,
        }

    def to_json(self) -> str:
        """Deterministic: sorted keys, fixed separators, ASCII only."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def digest(self) -> str:
        return hashlib.sha256(self.to_json().encode("ascii")).hexdigest()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RngState:
        return cls(
            version=d["version"],
            python=d["python"],
            numpy=d.get("numpy"),
            numpy_generators=d.get("numpy_generators") or {},
            torch_cpu=d.get("torch_cpu"),
            torch_cuda=d.get("torch_cuda"),
            torch_version=d.get("torch_version"),
            env=d.get("env") or {},
        )

    @classmethod
    def from_json(cls, text: str) -> RngState:
        return cls.from_dict(json.loads(text))


def capture_rng_state(
    *,
    numpy_generators: dict[str, Any] | None = None,
    include_torch: bool = True,
    torch_module: Any | None = None,
) -> RngState:
    """Snapshot the RNGs. Never advances any of them.

    Parameters
    ----------
    numpy_generators:
        Named ``numpy.random.Generator`` objects to include (a sampler's own
        generator, say). NumPy's global state does not cover these.
    include_torch:
        Set False to skip torch entirely.
    torch_module:
        Injected torch-like module (tests). Defaults to ``import torch`` if present.
    """
    version_py, internal, gauss = random.getstate()
    python = {"version": version_py, "internal": list(internal), "gauss_next": gauss}

    numpy_state: dict[str, Any] | None = None
    generators: dict[str, Any] = {}
    np = _import_optional("numpy")
    if np is not None:
        algo, keys, pos, has_gauss, cached = np.random.get_state()
        numpy_state = {
            "algorithm": algo,
            "keys": [int(k) for k in keys],
            "pos": int(pos),
            "has_gauss": int(has_gauss),
            "cached_gaussian": float(cached),
        }
        for name, gen in (numpy_generators or {}).items():
            generators[name] = gen.bit_generator.state

    torch_cpu = None
    torch_cuda: list[str] | None = None
    torch_version = None
    if include_torch:
        torch = torch_module if torch_module is not None else _import_optional("torch")
        if torch is not None:
            torch_version = str(getattr(torch, "__version__", "unknown"))
            torch_cpu = _tensor_to_b64(torch.get_rng_state())
            if torch.cuda.is_available():
                torch_cuda = [_tensor_to_b64(t) for t in torch.cuda.get_rng_state_all()]

    return RngState(
        version=RNG_STATE_VERSION,
        python=python,
        numpy=numpy_state,
        numpy_generators=generators,
        torch_cpu=torch_cpu,
        torch_cuda=torch_cuda,
        torch_version=torch_version,
        env={"PYTHONHASHSEED": os.environ.get("PYTHONHASHSEED")},
    )


def restore_rng_state(
    state: RngState,
    *,
    numpy_generators: dict[str, Any] | None = None,
    strict: bool = True,
    torch_module: Any | None = None,
) -> None:
    """Restore a captured state.

    ``strict=True`` (default) raises ``RngStateError`` if the state cannot be fully
    restored here (torch missing, CUDA device count differs). ``strict=False`` warns
    and restores whatever it can - use only when a partial restore is acceptable.
    """
    if state.version != RNG_STATE_VERSION:
        raise RngStateError(
            f"unsupported RNG state version {state.version!r}; this build reads "
            f"{RNG_STATE_VERSION!r}"
        )

    def _problem(msg: str) -> None:
        if strict:
            raise RngStateError(msg)
        warnings.warn(msg, RuntimeWarning, stacklevel=3)

    # ---- validate everything BEFORE mutating anything (all-or-nothing) ----------
    torch = torch_module if torch_module is not None else _import_optional("torch")
    restore_torch_cpu = state.torch_cpu is not None
    restore_cuda = state.torch_cuda is not None
    if restore_torch_cpu and torch is None:
        _problem("state carries torch RNG but torch is not importable here")
        restore_torch_cpu = restore_cuda = False
    if restore_cuda and torch is not None:
        if not torch.cuda.is_available():
            _problem("state carries CUDA RNG but CUDA is not available here")
            restore_cuda = False
        elif torch.cuda.device_count() != len(state.torch_cuda or []):
            _problem(
                f"state has {len(state.torch_cuda or [])} CUDA RNG states but "
                f"{torch.cuda.device_count()} device(s) are visible"
            )
            restore_cuda = False

    np = _import_optional("numpy")
    if state.numpy is not None and np is None:
        _problem("state carries NumPy RNG but numpy is not importable here")
    for name in state.numpy_generators:
        if not numpy_generators or name not in numpy_generators:
            _problem(f"state carries NumPy Generator {name!r} but no Generator was provided")

    # ---- restore ---------------------------------------------------------------
    random.setstate(
        (state.python["version"], tuple(state.python["internal"]), state.python["gauss_next"])
    )
    if state.numpy is not None and np is not None:
        n = state.numpy
        np.random.set_state(
            (
                n["algorithm"],
                np.array(n["keys"], dtype=np.uint32),
                n["pos"],
                n["has_gauss"],
                n["cached_gaussian"],
            )
        )
    for name, gen_state in state.numpy_generators.items():
        if numpy_generators and name in numpy_generators:
            numpy_generators[name].bit_generator.state = gen_state
    if restore_torch_cpu:
        torch.set_rng_state(_b64_to_tensor(torch, state.torch_cpu))
    if restore_cuda:
        torch.cuda.set_rng_state_all([_b64_to_tensor(torch, s) for s in state.torch_cuda])


def save_rng_state(state: RngState, path: Path | str) -> Path:
    """Write the deterministic JSON form. Same state -> same bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.to_json() + "\n", encoding="utf-8")
    return path


def load_rng_state(path: Path | str) -> RngState:
    return RngState.from_json(Path(path).read_text(encoding="utf-8"))
