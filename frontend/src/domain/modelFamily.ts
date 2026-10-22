// Which kind of model answered a row, read from the row's own `model_id`, and whether a row
// routed to KERMT was answered by XGBoost instead. Provenance only: no family is better, and
// nothing here ranks, colours or orders by it (AGENTS.md rules 1 and 3).
import type { EndpointPrediction } from "../types/contracts";
import { STUB_MODEL_ID } from "./endpoints";

export type ModelFamily = "xgboost" | "kermt" | "stub" | "rule_based" | "other";

export function modelFamily(modelId: string): ModelFamily {
  if (modelId === STUB_MODEL_ID) return "stub";
  if (modelId.startsWith("mars-xgboost")) return "xgboost";
  if (modelId.startsWith("mars-kermt")) return "kermt";
  if (modelId.startsWith("rdkit-")) return "rule_based";
  return "other";
}

/** Short text for the Source column. Stub rows say "" because the hatch and STUB tag already do. */
export function familyLabel(modelId: string): string {
  switch (modelFamily(modelId)) {
    case "xgboost":
      return "XGBoost";
    case "kermt":
      return "KERMT";
    case "rule_based":
      return "RDKit";
    case "stub":
      return "";
    default:
      return modelId;
  }
}

/** The deployment routes this endpoint to KERMT, but a real XGBoost model answered it for this
 *  request (the KERMT service did not answer). A stub-served row is a different state, not this one. */
export function servedByFallback(
  prediction: Pick<EndpointPrediction, "endpoint" | "model_id"> | undefined,
  kermtEndpoints: readonly string[],
): boolean {
  return !!prediction && kermtEndpoints.includes(prediction.endpoint) && modelFamily(prediction.model_id) === "xgboost";
}

export function fallbackCount(
  predictions: readonly Pick<EndpointPrediction, "endpoint" | "model_id">[],
  kermtEndpoints: readonly string[],
): number {
  return predictions.filter((p) => servedByFallback(p, kermtEndpoints)).length;
}
