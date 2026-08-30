// Hand-mirrored from contracts/mars_contracts/*.py (Phase 0 lock).
// If these drift from the Python contracts, that's a sync bug — flag it at the next handoff.

export type Endpoint =
  | "solubility_logs" | "lipophilicity_logp" | "caco2_permeability" | "hia_absorption"
  | "pgp_inhibition" | "bbb_permeability" | "ppb_binding" | "cyp3a4_inhibition"
  | "cyp2d6_inhibition" | "cyp2c9_inhibition" | "clearance_microsomal"
  | "herg_cardiotoxicity" | "ames_mutagenicity" | "dili_liver_injury" | "synthetic_accessibility";

export interface EndpointPrediction {
  endpoint: Endpoint;
  value: number;
  unit: string | null;
  confidence_low: number;
  confidence_high: number;
  in_domain: boolean;
  knn_distance: number;
}

export interface PredictionResponse {
  smiles_input: string;
  smiles_standardized: string;
  molecule_id: string;
  predictions: EndpointPrediction[];
  model_version: string;
  served_at: string;
  cache_hit: boolean;
}
