// Reconcile a response against the canonical roster (ADR-008). Every endpoint
// gets a row whether or not the service returned it; absence becomes a
// not_returned row, never a gap. Counts reconcile over the ML endpoints only —
// the rule-based synthetic-accessibility score is shown but not counted, because
// it is computed, not predicted (maintainer decision, Q1/Q2).
import type { Endpoint, EndpointPrediction, PredictionResponse } from "../types/contracts";
import {
  ALL_ENDPOINTS,
  DISPLAY_GROUP_LABEL,
  DISPLAY_GROUP_ORDER,
  ENDPOINT_METADATA,
  ML_ENDPOINTS,
  STUB_MODEL_ID,
  displayGroupOf,
  type DisplayGroup,
  type EndpointMeta,
} from "./endpoints";
import { deriveRowState, reliabilityOf, type EndpointRowState, type Reliability } from "./rowState";

export interface Row {
  endpoint: Endpoint;
  meta: EndpointMeta;
  prediction?: EndpointPrediction;
  state: EndpointRowState;
  reliability: Reliability;
}

export interface RowGroup {
  group: DisplayGroup;
  label: string;
  cluster: string;
  rows: Row[];
}

export interface Reconciliation {
  groups: RowGroup[];
  rows: Row[]; // flat, in display order — the roving-focus sequence
  counts: {
    requested: number;
    returned: number;
    outOfDomain: number;
    stubServed: number;
  };
}

const GROUP_CLUSTER_FALLBACK: Partial<Record<DisplayGroup, string>> = {
  "rule-based": "no model, no applicability domain",
};

export function reconcile(
  response: PredictionResponse,
  requested: Endpoint[] = ML_ENDPOINTS,
): Reconciliation {
  const byEndpoint = new Map<Endpoint, EndpointPrediction>();
  for (const p of response.predictions) byEndpoint.set(p.endpoint, p);

  const rowFor = (endpoint: Endpoint): Row => {
    const meta = ENDPOINT_METADATA[endpoint];
    const prediction = byEndpoint.get(endpoint);
    const state = deriveRowState(meta, prediction);
    return { endpoint, meta, prediction, state, reliability: reliabilityOf(state) };
  };

  const allRows = ALL_ENDPOINTS.map(rowFor);

  const groups: RowGroup[] = DISPLAY_GROUP_ORDER.map((group) => {
    const rows = allRows.filter((r) => displayGroupOf(r.endpoint) === group);
    const clusters = Array.from(
      new Set(rows.map((r) => r.meta.cluster).filter((c): c is string => !!c)),
    );
    const cluster =
      GROUP_CLUSTER_FALLBACK[group] ??
      (clusters.length ? `cluster${clusters.length > 1 ? "s" : ""} ${clusters.join(", ")}` : "");
    return { group, label: DISPLAY_GROUP_LABEL[group], cluster, rows };
  }).filter((g) => g.rows.length > 0);

  const requestedMl = requested.filter((e) => ENDPOINT_METADATA[e].taskType !== "rule_based");
  const mlPredictions = requestedMl
    .map((e) => byEndpoint.get(e))
    .filter((p): p is EndpointPrediction => !!p);

  const counts = {
    requested: requestedMl.length,
    returned: mlPredictions.length,
    outOfDomain: mlPredictions.filter((p) => !p.in_domain && p.model_id !== STUB_MODEL_ID).length,
    stubServed: mlPredictions.filter((p) => p.model_id === STUB_MODEL_ID).length,
  };

  return { groups, rows: allRows, counts };
}
