// The single pure function that decides an endpoint row's trustworthiness.
// Nothing else in the app is allowed to decide these states (ARCHITECTURE.md).
// This is what makes UX principle 1 enforceable: one place, pure, unit-testable.
import type { EndpointPrediction } from "../types/contracts";
import { STUB_MODEL_ID, type EndpointMeta } from "./endpoints";

export type EndpointRowState =
  | { kind: "ok" }
  | { kind: "out_of_domain"; knnDistance: number }
  | { kind: "stub_served"; modelId: string }
  | { kind: "not_returned" } // asked for, the service did not answer: a service-side absence
  | { kind: "not_requested" } // left out of the request by the user: a choice, never a failure (ADR-028)
  | { kind: "rule_based" };

export function deriveRowState(
  meta: EndpointMeta,
  prediction: EndpointPrediction | undefined,
  requested = true,
): EndpointRowState {
  // Absence has two causes and they must never share a word: NOT RETURNED means the
  // service failed to answer a question we asked (ADR-019 relies on that); NOT
  // REQUESTED means we did not ask. A prediction that is present is described as
  // such whatever was requested.
  if (!prediction) return requested ? { kind: "not_returned" } : { kind: "not_requested" };
  if (meta.taskType === "rule_based") return { kind: "rule_based" };
  // A stub value is "not a real prediction" — a more fundamental fact than
  // applicability domain, which does not apply without a promoted model.
  if (prediction.model_id === STUB_MODEL_ID)
    return { kind: "stub_served", modelId: prediction.model_id };
  if (!prediction.in_domain)
    return { kind: "out_of_domain", knnDistance: prediction.knn_distance };
  return { kind: "ok" };
}

// Reliability is a single visual channel (the left edge + a tag). It never
// touches the value cell (ADR-006). `null` = no edge, no tag.
export type Reliability = "ood" | "stub" | "notreturned" | "notrequested" | "rule" | null;

export function reliabilityOf(state: EndpointRowState): Reliability {
  switch (state.kind) {
    case "out_of_domain":
      return "ood";
    case "stub_served":
      return "stub";
    case "not_returned":
      return "notreturned";
    case "not_requested":
      return "notrequested";
    case "rule_based":
      return "rule";
    default:
      return null;
  }
}
