"""PAINS and Brenk structural-alert matching, in one place (frontend ADR-034 item 3).

Both catalogs ship inside the `rdkit` wheel (`FilterCatalogParams`), so this adds no dependency. The
serving layer reports which alerts a molecule matches (`serve.properties`); the explainability validation
(`ml/eval/explain_validation.py`, on `feat/explainability`) asks where they match. Both call
`alert_matches`, so there is one definition of "an alert" and one catalog cache.

An alert is a substructure match, not a prediction. PAINS (Baell & Holloway 2010, J. Med. Chem. 53:2719)
concerns frequent-hitter behaviour in assays, not toxicity, and a 2017 critique found most compounds it flags
show no interference (Capuzzi, Muratov & Tropsha, J. Chem. Inf. Model. 57:417). Brenk (Brenk et al. 2008,
ChemMedChem 3:435) lists unwanted functionality for screening libraries.
"""

from __future__ import annotations

from functools import cache

from rdkit import Chem
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams

# Catalog labels as they are shown and as the API contract spells them.
ALERT_CATALOGS: dict[str, FilterCatalogParams.FilterCatalogs] = {
    "PAINS": FilterCatalogParams.FilterCatalogs.PAINS,
    "Brenk": FilterCatalogParams.FilterCatalogs.BRENK,
}


@cache
def _catalog(name: str) -> FilterCatalog:
    params = FilterCatalogParams()
    params.AddCatalog(ALERT_CATALOGS[name])
    return FilterCatalog(params)


def alert_matches(
    mol: Chem.Mol, catalogs: dict[str, FilterCatalogParams.FilterCatalogs] = ALERT_CATALOGS
) -> list[tuple[str, str, set[int]]]:
    """(catalog, alert description, matched atoms) for every PAINS/Brenk match in `mol`."""
    out: list[tuple[str, str, set[int]]] = []
    for name in catalogs:
        catalog = _catalog(name) if name in ALERT_CATALOGS else _build(name, catalogs[name])
        for entry in catalog.GetMatches(mol):
            for match in entry.GetFilterMatches(mol):
                out.append((name, entry.GetDescription(), {mol_idx for _q, mol_idx in match.atomPairs}))
    return out


def _build(name: str, which: FilterCatalogParams.FilterCatalogs) -> FilterCatalog:
    params = FilterCatalogParams()
    params.AddCatalog(which)
    return FilterCatalog(params)


def distinct_alerts(mol: Chem.Mol) -> list[tuple[str, str]]:
    """The (catalog, alert name) pairs `mol` matches, each once, in catalog then name order."""
    return sorted({(catalog, name) for catalog, name, _atoms in alert_matches(mol)})
