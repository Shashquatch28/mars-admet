// Mirror of contracts/mars_contracts/*.py (Phase 0 lock). Drift from the Python
// contract is a sync bug — ADR-009 proposes a CI check that fails the build on
// drift. Field names and shapes match prediction.py / endpoints.py / api.py.

export type TaskType = "regression" | "classification" | "rule_based";

export type EndpointCategory =
  | "absorption"
  | "distribution"
  | "metabolism"
  | "excretion"
  | "toxicity";

export type Endpoint =
  | "solubility_logs"
  | "lipophilicity_logp"
  | "caco2_permeability"
  | "hia_absorption"
  | "pgp_inhibition"
  | "bbb_permeability"
  | "ppb_binding"
  | "cyp3a4_inhibition"
  | "cyp2d6_inhibition"
  | "cyp2c9_inhibition"
  | "clearance_microsomal"
  | "herg_cardiotoxicity"
  | "ames_mutagenicity"
  | "dili_liver_injury"
  | "synthetic_accessibility";

export interface PredictionRequest {
  smiles: string;
  endpoints?: Endpoint[] | null;
}

export interface EndpointPrediction {
  endpoint: Endpoint;
  value: number;
  unit: string | null;
  confidence_low: number;
  confidence_high: number;
  in_domain: boolean;
  knn_distance: number;
  // Additive field (M3). Which trained artifact served THIS endpoint;
  // "stub-v0" means no promoted model. Defaults to the stub so older
  // callers are unaffected (prediction.py).
  model_id: string;
  // PROPOSED additive field (OPEN_QUESTIONS Q19): the per-endpoint
  // applicability-domain threshold (90th-pct of the training set's own 5-NN
  // distances, Module 5) the gauge draws its tick at. Not in the contract yet;
  // the UI reads it when present and falls back to a local table otherwise.
  ad_threshold?: number | null;
}

export interface PredictionResponse {
  smiles_input: string;
  smiles_standardized: string;
  molecule_id: string;
  predictions: EndpointPrediction[];
  model_version: string;
  served_at: string; // ISO datetime
  cache_hit: boolean;
}

// --- batch (api.py) ---
export interface BatchRowResult {
  row_index: number;
  smiles_input: string;
  ok: boolean;
  error?: string | null;
  prediction?: PredictionResponse | null;
}
export interface BatchPredictResponse {
  job_id?: string | null;
  status: "done" | "queued" | "running" | "failed";
  total: number;
  completed: number;
  results?: BatchRowResult[] | null;
}

// --- compare (api.py) ---
export interface CompareResponse {
  molecules: PredictionResponse[];
  // per_endpoint_winner is intentionally NOT consumed anywhere in the UI
  // (ADR-007): direction-of-good is unresolved. Typed for completeness only.
  per_endpoint_winner?: Record<Endpoint, number> | null;
}
