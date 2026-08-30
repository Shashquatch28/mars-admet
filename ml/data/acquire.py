"""
Module 1 §1 — pull all 14 TDC datasets, pin package version + snapshot hashes
to a lockfile for reproducibility. Fill in as Phase 1 (Milestone 1, Module 1) work.
"""

from mars_contracts import Endpoint

# TDC dataset name per endpoint (Module 2 table) — fill in loader calls here.
TDC_DATASET_MAP = {
    Endpoint.SOLUBILITY: "Solubility_AqSolDB",
    Endpoint.LIPOPHILICITY: "Lipophilicity_AstraZeneca",
    Endpoint.CACO2: "Caco2_Wang",
    Endpoint.HIA: "HIA_Hou",
    Endpoint.PGP: "Pgp_Broccatelli",
    Endpoint.BBB: "BBB_Martins",
    Endpoint.PPB: "PPBR_AZ",
    Endpoint.CYP3A4: "CYP3A4_Veith",
    Endpoint.CYP2D6: "CYP2D6_Veith",
    Endpoint.CYP2C9: "CYP2C9_Veith",
    Endpoint.CLEARANCE: "Clearance_Microsome_AZ",
    Endpoint.HERG: "hERG_Karim",
    Endpoint.AMES: "AMES",
    Endpoint.DILI: "DILI",  # + DILIst augmentation per Module 1 §6
}

if __name__ == "__main__":
    print(f"{len(TDC_DATASET_MAP)} endpoints mapped to TDC datasets. Implement PyTDC pulls here.")
