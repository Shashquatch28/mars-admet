"""Module 12 batch upload — SDF support (blueprint: "CSV/SDF upload").

RDKit is only installed in the production/container environment (see
`ml/requirements-serving.txt`, installed via `api/Dockerfile`) — the root
`.venv` used for fast local tests deliberately does not have it (see
`documentation/AIMS/mars-aims-and-envs.md`). `sdf_available` lets
`routers/batch.py` distinguish "no rows parsed because the file was empty"
from "can't parse SDF at all in this environment" and return the right
status code for each, rather than silently mis-reporting one as the other.
"""

from __future__ import annotations

import io

try:
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")  # SDF parse errors are handled per-record below, not logged to stderr
    sdf_available = True
except ImportError:
    sdf_available = False


def parse_sdf(content: bytes) -> list[str]:
    """Extract one SMILES per SDF record, in file order.

    A record that fails to parse becomes an empty string at its position
    (consistent with `_parse_csv`'s "" for a missing column value) — the
    caller's existing per-row `ok=False` handling in `batch.py` treats an
    empty/invalid SMILES as a non-blocking per-row error, not a batch
    failure. Raises `RuntimeError` if called when `sdf_available` is False;
    callers must check that first.
    """
    if not sdf_available:
        raise RuntimeError("rdkit is not installed in this environment — cannot parse SDF")

    supplier = Chem.ForwardSDMolSupplier(io.BytesIO(content), sanitize=True, removeHs=False)
    smiles: list[str] = []
    for mol in supplier:
        if mol is None:
            smiles.append("")
            continue
        smiles.append(Chem.MolToSmiles(mol))
    return smiles
