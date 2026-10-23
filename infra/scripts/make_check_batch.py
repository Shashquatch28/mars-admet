"""Write a CSV of N distinct, valid SMILES for the post-deploy batch check (documentation/DEPLOY.md, check C-7).

    python infra/scripts/make_check_batch.py 300 check_batch_300.csv

The molecules are simple chains with a head group (butanol, pentanoic acid, hexylamine, ...), so every row is a
different molecule that really goes through the models; repeating one SMILES would be answered from the
prediction cache and prove nothing about the worker. Standard library only.
"""

from __future__ import annotations

import csv
import sys

HEADS = ["O", "N", "C(=O)O", "C#N", "OC", "Br", "Cl", "F", "C(=O)N", "S", "OC(C)=O", "C(F)(F)F", "N(C)C", "C=O", "C(=O)OC", "OCC"]


def molecules(count: int) -> list[str]:
    out: list[str] = []
    length = 1
    while len(out) < count:
        for head in HEADS:
            if len(out) == count:
                break
            out.append("C" * length + head)
        length += 1
    return out


def main(argv: list[str]) -> int:
    count, path = int(argv[1]), argv[2]
    rows = molecules(count)
    assert len(set(rows)) == count
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["smiles"])
        writer.writerows([[smi] for smi in rows])
    print(f"wrote {count} distinct SMILES to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
