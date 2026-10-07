// Prototype fixture — illustrative values only, NOT model output. The UI renders
// a full-width "design prototype" strip whenever a fixture is in use (ADR-010).
// Celecoxib, matching the design comps. clearance_microsomal is intentionally
// absent so the roster shows a not_returned row; cyp2c9 is stub-served.
// ad_threshold mirrors the contract field (Q19): a number where the endpoint has an
// applicability-domain index, null for stub-served and rule-based rows. The 0.58 below
// is an illustrative fixture value, not a measured Module 5 cutoff.
import type { PredictionResponse } from "../types/contracts";

export const CELECOXIB_SMILES =
  "CC1=CC=C(C=C1)C1=CC(=NN1C1=CC=C(C=C1)S(N)(=O)=O)C(F)(F)F";
export const CELECOXIB_STD =
  "Cc1ccc(-c2cc(C(F)(F)F)nn2-c2ccc(S(N)(=O)=O)cc2)cc1";

const REAL = "mars-xgboost-ecfp-v1";
const REAL_DESC = "mars-xgboost-ecfp-desc-v1";
const THR = 0.58; // illustrative fixture value

export const FIXTURE_RESPONSE: PredictionResponse = {
  smiles_input: CELECOXIB_SMILES,
  smiles_standardized: CELECOXIB_STD,
  molecule_id: "a3f2c81d9b4e6027",
  model_version: "mars-routing@v0.3.1",
  served_at: "2026-10-01T08:14:07Z",
  cache_hit: false,
  predictions: [
    { endpoint: "solubility_logs", value: -4.18, unit: "logS", confidence_low: -4.55, confidence_high: -3.81, in_domain: true, knn_distance: 0.33, model_id: REAL_DESC, ad_threshold: THR },
    { endpoint: "lipophilicity_logp", value: 3.42, unit: "logP", confidence_low: 3.1, confidence_high: 3.74, in_domain: true, knn_distance: 0.29, model_id: REAL_DESC, ad_threshold: THR },
    { endpoint: "caco2_permeability", value: -5.06, unit: "log cm/s", confidence_low: -5.61, confidence_high: -4.51, in_domain: false, knn_distance: 0.71, model_id: REAL_DESC, ad_threshold: THR },
    { endpoint: "hia_absorption", value: 0.94, unit: null, confidence_low: 0.87, confidence_high: 0.99, in_domain: true, knn_distance: 0.41, model_id: REAL, ad_threshold: THR },
    { endpoint: "pgp_inhibition", value: 0.31, unit: null, confidence_low: 0.24, confidence_high: 0.39, in_domain: true, knn_distance: 0.37, model_id: REAL, ad_threshold: THR },
    { endpoint: "bbb_permeability", value: 0.22, unit: null, confidence_low: 0.14, confidence_high: 0.31, in_domain: false, knn_distance: 0.66, model_id: REAL, ad_threshold: THR },
    { endpoint: "ppb_binding", value: 96.4, unit: "% bound", confidence_low: 94.8, confidence_high: 98.0, in_domain: true, knn_distance: 0.44, model_id: REAL_DESC, ad_threshold: THR },
    { endpoint: "cyp3a4_inhibition", value: 0.68, unit: null, confidence_low: 0.6, confidence_high: 0.76, in_domain: true, knn_distance: 0.39, model_id: REAL, ad_threshold: THR },
    { endpoint: "cyp2d6_inhibition", value: 0.12, unit: null, confidence_low: 0.06, confidence_high: 0.19, in_domain: true, knn_distance: 0.33, model_id: REAL, ad_threshold: THR },
    { endpoint: "cyp2c9_inhibition", value: 0.85, unit: null, confidence_low: 0.78, confidence_high: 0.92, in_domain: true, knn_distance: 0.0, model_id: "stub-v0", ad_threshold: null },
    // clearance_microsomal omitted -> not_returned
    { endpoint: "herg_cardiotoxicity", value: 0.41, unit: null, confidence_low: 0.33, confidence_high: 0.49, in_domain: true, knn_distance: 0.36, model_id: REAL, ad_threshold: THR },
    { endpoint: "ames_mutagenicity", value: 0.07, unit: null, confidence_low: 0.03, confidence_high: 0.13, in_domain: true, knn_distance: 0.3, model_id: REAL, ad_threshold: THR },
    { endpoint: "dili_liver_injury", value: 0.55, unit: null, confidence_low: 0.47, confidence_high: 0.63, in_domain: true, knn_distance: 0.48, model_id: REAL, ad_threshold: THR },
    { endpoint: "synthetic_accessibility", value: 2.84, unit: "SA score", confidence_low: 2.84, confidence_high: 2.84, in_domain: true, knn_distance: 0.0, model_id: "rdkit-sascore", ad_threshold: null },
  ],
};

// Roster-only response used while a real request is in flight: no predictions,
// so every row reconciles to a placeholder the loading state renders.
export function emptyResponse(smiles: string): PredictionResponse {
  return {
    smiles_input: smiles,
    smiles_standardized: smiles,
    molecule_id: "",
    model_version: "mars-routing@v0.3.1",
    served_at: new Date().toISOString(),
    cache_hit: false,
    predictions: [],
  };
}
