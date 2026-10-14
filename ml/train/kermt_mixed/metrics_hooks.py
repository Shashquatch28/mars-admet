"""
Per-epoch record sink for the mixed trainer.

Runs inside the container, where W&B and ``ExperimentRun`` are not available (and
must not become a second tracking system — blueprint Module 11). It writes
append-only JSONL under the run directory; the host side
(``train.train_kermt_mixed``) reads it back and feeds ``ExperimentRun`` / W&B.

One line per epoch, plus a single ``{"event": "summary", ...}`` line at the end.
Flushed on every write so a killed run keeps everything up to the last epoch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _clean(obj: Any) -> Any:
    """JSON-safe: tensors/ndarrays/numpy scalars -> python; NaN/Inf -> None."""
    if hasattr(obj, "tolist"):
        obj = obj.tolist()
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        return None
    return obj


class JsonlLogger:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")

    def write(self, record: dict[str, Any]) -> None:
        self._fh.write(json.dumps(_clean(record), sort_keys=True) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> JsonlLogger:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
