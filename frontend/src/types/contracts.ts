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
  // Regression value, or a classification score in [0,1]. A score is a bounded
  // model output, not a validated probability (ADR-023, prediction.py).
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
  // Additive field (Q19). The cutoff in_domain was judged against: the 90th
  // percentile of the training set's own 5-NN distances (Module 5), so
  // in_domain === (knn_distance <= ad_threshold). null when the endpoint has no
  // applicability-domain index (stub-served, rule-based): there is no tick to
  // draw and the client must not invent one.
  ad_threshold: number | null;
  // Additive fields (ADR-024). Regression endpoints only: heldout_error_level of the absolute errors the
  // promoted seeds made on molecules held out of their own training were at most heldout_error_halfwidth,
  // taken over heldout_error_n pooled residuals. One constant per endpoint, not a per-molecule interval.
  // null (or absent, in a response produced before they existed) means no band: show none, invent none.
  heldout_error_halfwidth?: number | null;
  heldout_error_level?: number | null;
  heldout_error_n?: number | null;
}

/** One PAINS or Brenk substructure match. A match is not a prediction; PAINS concerns assay interference, not toxicity. */
export interface StructuralAlert {
  catalog: "PAINS" | "Brenk";
  name: string;
}

/**
 * RDKit-computed properties of the standardized molecule (ADR-034 item 3). Not model predictions:
 * deterministic, no applicability domain, independent of which model answered. Plain numbers; no pass or
 * fail meaning is attached to any of them.
 */
export interface MoleculeProperties {
  mol_weight: number; // g/mol
  crippen_logp: number; // Wildman-Crippen, not Lipinski's CLogP
  h_bond_donors: number;
  h_bond_acceptors: number;
  tpsa: number; // A^2
  rotatable_bonds: number;
  qed?: number | null; // a published desirability function of eight properties, not a MARS prediction
  lipinski_criteria_exceeded: number; // 0 to 4 of the four rule-of-five limits
  alerts: StructuralAlert[];
}

export interface PredictionResponse {
  smiles_input: string;
  smiles_standardized: string;
  molecule_id: string;
  predictions: EndpointPrediction[];
  model_version: string;
  served_at: string; // ISO datetime
  cache_hit: boolean;
  /** Absent or null on a response that predates it (cached or saved earlier) and when the service has no RDKit. */
  properties?: MoleculeProperties | null;
}

// --- name (api.py, ADR-044) ---
// POST /name: what a name source says about one structure, with the source stated. `not_found` is an answer; `unavailable`
// is a failure of the source and is told apart from it. A name is never guessed and says nothing about a prediction.
export type NameStatus = "found" | "not_found" | "unavailable";
export interface NameRequest {
  smiles: string; // the service sends the source the molecule's InChIKey only, never this
}
export interface NameResponse {
  status: NameStatus;
  inchikey: string;
  source: string; // in words, e.g. "PubChem"
  source_record: string | null; // the source's own id, e.g. "CID 2244"
  source_url: string | null;
  preferred_name: string | null;
  iupac_name: string | null;
  synonyms: string[];
  reason: string | null; // only when unavailable
}

// --- conformer (conformer.py) ---
export interface ConformerAtom {
  element: string;
  x: number;
  y: number;
  z: number;
  partial_charge: number | null;
}
export interface ConformerBond {
  atom_index_1: number;
  atom_index_2: number;
  order: number; // 1, 1.5 (aromatic), 2, 3
}
// --- depict (api.py; the response is image/svg+xml, not JSON) ---
export interface DepictRequest {
  smiles: string; // drawn from its RDKit canonical form
}

export interface ConformerResponse {
  molecule_id: string;
  atoms: ConformerAtom[];
  bonds: ConformerBond[];
  energy_kcal_mol: number; // MMFF94 energy of the returned (lowest-energy) conformer
  sdf_block: string; // full SDF, handed to 3Dmol as-is
}

// --- explanation (explain.py, ADR-031) ---
// Signed attribution of the model's output; the sign is "pushed up / pushed down", never good or bad.
export type ExplainMethod = "tree_shap" | "integrated_gradients";
export type ExplainOutputSpace = "log_odds" | "score" | "native_unit";
export type ExplainJobState = "queued" | "running" | "done" | "failed" | "cancelled";
export interface FragmentAttribution {
  name: string;
  smarts: string;
  atom_indices: number[];
  score: number; // sum of member atoms; fragments overlap, so these do not add up
}
export interface DescriptorAttribution {
  name: string;
  value: number | null;
  score: number;
}
export interface ExplainResponse {
  molecule_id: string;
  endpoint: Endpoint;
  method: ExplainMethod;
  model_id: string; // equals the model_id of the prediction explained
  output_space: ExplainOutputSpace;
  unit: string | null;
  n_seeds: number;
  base_value: number;
  output_value: number;
  baseline: string; // the reference, in words
  atom_attributions: number[]; // one per atom of smiles_standardized, RDKit order, no hydrogens
  fragment_attributions: FragmentAttribution[];
  whole_molecule_attributions: DescriptorAttribution[];
  whole_molecule_rest: number;
  structure_total: number;
  whole_molecule_total: number;
  unmapped_total: number;
  completeness_error: number; // IG: the integration residual; TreeSHAP: the additivity error
  converged: boolean | null; // IG only: met the tolerance after the final step count; a result that did not is flagged, not hidden
  seed_agreement: number | null; // median pairwise cosine of the per-seed atom attributions; null for one seed
  n_steps: number | null;
  model_version: string;
}
// A KERMT-served explanation is a background job. 202 while queued or running; a done job is read as an
// ExplainResponse. No percentage and no estimate: the step count escalates adaptively (ADR-040).
export interface ExplainJobStatus {
  job_id: string;
  molecule_id: string;
  endpoint: Endpoint;
  state: ExplainJobState;
  queue_position: number | null;
  seeds_done: number;
  seeds_total: number;
  stage: string | null;
  elapsed_seconds: number;
  submitted_at: string; // ISO datetime
  error: string | null;
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
export interface CompareRequest {
  smiles: string[]; // 2 or 3
  endpoints?: Endpoint[] | null;
}
export interface CompareResponse {
  molecules: PredictionResponse[];
  // per_endpoint_winner is intentionally NOT consumed anywhere in the UI
  // (ADR-007): direction-of-good is unresolved. Typed for completeness only.
  per_endpoint_winner?: Record<Endpoint, number> | null;
}

// --- auth (auth.py) ---
// Session strategy is an HttpOnly cookie: no response body carries a token.
export interface RegisterRequest {
  email: string;
  password: string; // min 8 characters
  turnstile_token: string; // not wired in the client yet (ADR-022 item 6): the server skips verification when unset
}
export interface RegisterResponse {
  user_id: string;
}
export interface LoginRequest {
  email: string;
  password: string;
}
export interface LoginResponse {
  user_id: string;
}
// GET /auth/me. 401 means there is no valid session (ADR-022).
export interface MeResponse {
  user_id: string;
  email: string;
}

// --- persistence (persistence.py): Library and delete-account ---
// A saved molecule or report is a frozen snapshot of a response the user already
// received. It is never recomputed, so it carries the `model_version` it was made with.
export interface SaveMoleculeRequest {
  prediction: PredictionResponse; // exactly as received from /predict
  label?: string | null;
  notes?: string | null;
  tags?: string[];
}
export interface SaveReportRequest {
  type: string; // "single" | "batch"
  source_batch_job_id?: string | null; // provenance only, not a live dependency
  results: BatchPredictResponse | PredictionResponse; // the result set to freeze
  molecule_ids?: string[]; // references to separately saved molecules
  notes?: string | null;
  tags?: string[];
}
export interface SavedMoleculeResponse {
  id: string;
  smiles: string; // standardized SMILES, from predictions_snapshot
  label: string | null;
  notes: string | null;
  tags: string[];
  predictions_snapshot: PredictionResponse;
  model_version: string;
  created_at: string; // ISO datetime
  updated_at: string;
}
export interface SavedReportResponse {
  id: string;
  type: string; // "single" | "batch"
  source_batch_job_id: string | null;
  results_snapshot: Record<string, unknown>; // frozen BatchPredictResponse or PredictionResponse
  molecule_ids: string[];
  notes: string | null;
  tags: string[];
  created_at: string;
}
// Password reset (auth.py, ADR-043). Asking always answers 202 with no body, whether or not the address has an account;
// confirming answers 204 on success and 400 for any bad, used or expired token. Neither signs anyone in.
export interface PasswordResetRequestModel {
  email: string;
}
export interface PasswordResetConfirmRequest {
  token: string; // from the emailed link's fragment; single use
  new_password: string; // min 8 characters, at most 72 bytes
}
export interface DeleteAccountRequest {
  password: string; // re-confirmation before a cascading, irreversible delete
}

// --- limits (api.py) ---
// GET /limits (frontend ADR-034 item 8): the deployed policy numbers. UI copy that states a cap, a
// threshold or a retention period reads them from here and never from a constant.
export interface LimitsResponse {
  batch_size_cap: number;
  batch_interactive_threshold: number;
  batch_result_retention_hours: number;
  anon_predict_rate_per_minute: number;
  password_reset_ttl_minutes: number;
}

// --- generations (api.py) ---
// GET /generations (ADR-026). `available` is [active] until a second generation exists,
// so a picker built from it never offers a choice that is not real.
export interface GenerationsResponse {
  active: string;
  available: string[];
  /** Endpoints this deployment routes to KERMT; empty when KERMT serving is off. Provenance, not a ranking. */
  kermt_endpoints: string[];
}
