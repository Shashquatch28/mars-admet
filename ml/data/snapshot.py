"""
Deterministic snapshot hashing for MARS dataset provenance (blueprint Module 1
§5, Module 11 §5/§6).

Two hash kinds:

  * ``sha256_file`` — byte hash of an exact file as delivered/written. Detects
    any change to the stored artifact.

  * ``canonical_rows_digest`` — an *order-independent* content hash over
    ``(smiles, label)`` pairs. PyTDC does not guarantee stable row ordering
    across versions or machines, so a raw byte hash of ``df.to_csv()`` would be
    fragile. This digest canonicalizes each row and sorts before hashing, so it
    identifies the dataset *content* regardless of row order or CSV formatting.

Standard library only — usable from the isolated acquisition environment.
"""

from __future__ import annotations

import csv as _csv
import hashlib
from collections.abc import Iterable, Iterator
from pathlib import Path

_UNIT_SEP = "\x1f"  # between fields of a row
_REC_SEP = "\x1e"  # between rows

DIGEST_SCHEME = "mars-canonical-rows-v1"


def sha256_file(path: str | Path, *, chunk_size: int = 1 << 20) -> str:
    """SHA-256 hex digest of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_label(value: object) -> str:
    """Format one label value deterministically.

    The same logical value hashes identically no matter how it reached us — a
    pandas ``float64`` ``1.0``, the CSV string ``"1.0"``, and the int ``1`` all
    canonicalize to ``"1"``. Non-integer floats use the shortest round-tripping
    ``repr`` (stable across platforms for IEEE-754 doubles). ``None`` / NaN /
    empty -> ``"\\x00null"``.
    """
    null = "\x00null"
    if value is None:
        return null
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value:  # NaN
            return null
        return str(int(value)) if value.is_integer() else repr(value)
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null"}:
        return null
    # numeric strings (CSV round-trip) collapse to the same tokens as real numbers
    try:
        return str(int(text))
    except ValueError:
        pass
    try:
        f = float(text)
    except ValueError:
        return text
    if f != f:
        return null
    return str(int(f)) if f.is_integer() else repr(f)


def canonical_rows_digest(rows: Iterable[tuple[str, object]]) -> str:
    """Order-independent SHA-256 over canonicalized ``(smiles, label)`` rows.

    ``smiles`` is used verbatim except for surrounding whitespace — this is the
    *raw* SMILES as delivered by TDC, before Module 3 standardization, on
    purpose: the snapshot must identify what we downloaded, not what we derived.
    """
    encoded: list[str] = []
    for smiles, label in rows:
        s = (smiles or "").strip() if isinstance(smiles, str) else str(smiles).strip()
        encoded.append(s + _UNIT_SEP + canonical_label(label))
    encoded.sort()
    h = hashlib.sha256()
    h.update(DIGEST_SCHEME.encode("utf-8"))
    h.update(_REC_SEP.encode("utf-8"))
    h.update(_REC_SEP.join(encoded).encode("utf-8"))
    return h.hexdigest()


def iter_csv_rows(
    path: str | Path, smiles_col: str, label_col: str
) -> Iterator[tuple[str, str]]:
    """Yield ``(smiles, label)`` string pairs from a CSV with a header row."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = _csv.DictReader(fh)
        if reader.fieldnames is None or smiles_col not in reader.fieldnames:
            raise KeyError(f"{path}: column {smiles_col!r} not in {reader.fieldnames}")
        for row in reader:
            yield row[smiles_col], row[label_col]


def canonical_csv_digest(path: str | Path, smiles_col: str, label_col: str) -> str:
    """Order-independent content digest of a persisted CSV.

    This is the canonical way MARS identifies a stored dataset snapshot: the hash
    is defined over *what was written to disk*, so re-deriving it during
    verification uses the identical code path and cannot drift from the value
    recorded at acquisition time.
    """
    return canonical_rows_digest(iter_csv_rows(path, smiles_col, label_col))


def canonical_df_digest(df, smiles_col: str, label_col: str) -> str:
    """``canonical_rows_digest`` for a pandas DataFrame (pandas imported lazily).

    Prefer ``canonical_csv_digest`` on the persisted file for provenance hashes;
    this helper is for in-memory checks only.
    """
    rows = zip(df[smiles_col].tolist(), df[label_col].tolist(), strict=True)
    return canonical_rows_digest(rows)
