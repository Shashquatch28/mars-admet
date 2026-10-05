// Canonical roster + metadata, mirrored from contracts/mars_contracts/endpoints.py.
// This is the client-side source of the full endpoint roster (ADR-008): the UI
// reconciles every response against it and never derives the roster from a
// response.
import type { Endpoint, EndpointCategory, TaskType } from "../types/contracts";

export interface EndpointMeta {
  taskType: TaskType;
  category: EndpointCategory;
  cluster: string | null;
}

// Order matches the Python Endpoint enum.
export const ALL_ENDPOINTS: Endpoint[] = [
  "solubility_logs",
  "lipophilicity_logp",
  "caco2_permeability",
  "hia_absorption",
  "pgp_inhibition",
  "bbb_permeability",
  "ppb_binding",
  "cyp3a4_inhibition",
  "cyp2d6_inhibition",
  "cyp2c9_inhibition",
  "clearance_microsomal",
  "herg_cardiotoxicity",
  "ames_mutagenicity",
  "dili_liver_injury",
  "synthetic_accessibility",
];

export const ENDPOINT_METADATA: Record<Endpoint, EndpointMeta> = {
  solubility_logs: { taskType: "regression", category: "absorption", cluster: "absorption_distribution" },
  lipophilicity_logp: { taskType: "regression", category: "absorption", cluster: "absorption_distribution" },
  caco2_permeability: { taskType: "regression", category: "absorption", cluster: "absorption_distribution" },
  hia_absorption: { taskType: "classification", category: "absorption", cluster: "absorption_distribution" },
  pgp_inhibition: { taskType: "classification", category: "absorption", cluster: "absorption_distribution" },
  bbb_permeability: { taskType: "classification", category: "distribution", cluster: "absorption_distribution" },
  ppb_binding: { taskType: "regression", category: "distribution", cluster: "absorption_distribution" },
  cyp3a4_inhibition: { taskType: "classification", category: "metabolism", cluster: "metabolism" },
  cyp2d6_inhibition: { taskType: "classification", category: "metabolism", cluster: "metabolism" },
  cyp2c9_inhibition: { taskType: "classification", category: "metabolism", cluster: "metabolism" },
  clearance_microsomal: { taskType: "regression", category: "excretion", cluster: "metabolism" },
  herg_cardiotoxicity: { taskType: "classification", category: "toxicity", cluster: "toxicity" },
  ames_mutagenicity: { taskType: "classification", category: "toxicity", cluster: "toxicity" },
  dili_liver_injury: { taskType: "classification", category: "toxicity", cluster: "dili_standalone" },
  // In the contract SA is filed under ABSORPTION; the UI shows it in its own
  // RULE-BASED group (maintainer decision, OPEN_QUESTIONS Q2). Grouping is by
  // task_type, so this metadata stays a faithful mirror.
  synthetic_accessibility: { taskType: "rule_based", category: "absorption", cluster: null },
};

export const ML_ENDPOINTS: Endpoint[] = ALL_ENDPOINTS.filter(
  (e) => ENDPOINT_METADATA[e].taskType !== "rule_based",
);

// Display groups, in order. Rule-based endpoints are pulled into their own
// trailing group regardless of their contract category.
export type DisplayGroup =
  | "absorption"
  | "distribution"
  | "metabolism"
  | "excretion"
  | "toxicity"
  | "rule-based";

export const DISPLAY_GROUP_ORDER: DisplayGroup[] = [
  "absorption",
  "distribution",
  "metabolism",
  "excretion",
  "toxicity",
  "rule-based",
];

export const DISPLAY_GROUP_LABEL: Record<DisplayGroup, string> = {
  absorption: "Absorption",
  distribution: "Distribution",
  metabolism: "Metabolism",
  excretion: "Excretion",
  toxicity: "Toxicity",
  "rule-based": "Rule-based",
};

export function displayGroupOf(e: Endpoint): DisplayGroup {
  const meta = ENDPOINT_METADATA[e];
  if (meta.taskType === "rule_based") return "rule-based";
  return meta.category;
}

// The classification probability axis MARS treats as genuinely bounded.
export const PROB_DOMAIN: readonly [number, number] = [0, 1];

// Applicability-domain gauge threshold per endpoint: the 90th-percentile of the
// training set's own internal 5-NN distances (blueprint Module 5). This is real,
// validated per-endpoint metadata that is NOT yet in the prediction response —
// it must be sourced from the ML artifacts (or added to the API). The values
// below are placeholders for the prototype. See OPEN_QUESTIONS Q19.
export const AD_THRESHOLD: Partial<Record<Endpoint, number>> = {
  solubility_logs: 0.58,
  lipophilicity_logp: 0.58,
  caco2_permeability: 0.58,
  hia_absorption: 0.58,
  pgp_inhibition: 0.58,
  bbb_permeability: 0.58,
  ppb_binding: 0.58,
  cyp3a4_inhibition: 0.58,
  cyp2d6_inhibition: 0.58,
  cyp2c9_inhibition: 0.58,
  clearance_microsomal: 0.58,
  herg_cardiotoxicity: 0.58,
  ames_mutagenicity: 0.58,
  dili_liver_injury: 0.58,
};

export const STUB_MODEL_ID = "stub-v0";

// Display unit per endpoint for the results column. Classification carries no
// unit in the contract (null) — the axis is labelled "probability" in the UI.
// Used for the not_returned row too, where there is no prediction to read a unit
// from.
export const DISPLAY_UNIT: Record<Endpoint, string> = {
  solubility_logs: "logS",
  lipophilicity_logp: "logP",
  caco2_permeability: "log cm/s",
  hia_absorption: "probability",
  pgp_inhibition: "probability",
  bbb_permeability: "probability",
  ppb_binding: "% bound",
  cyp3a4_inhibition: "probability",
  cyp2d6_inhibition: "probability",
  cyp2c9_inhibition: "probability",
  clearance_microsomal: "mL/min/kg",
  herg_cardiotoxicity: "probability",
  ames_mutagenicity: "probability",
  dili_liver_injury: "probability",
  synthetic_accessibility: "SA score",
};
