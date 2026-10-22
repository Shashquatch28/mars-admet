// Which model answered a value, as text read from the row's own model_id, plus a dagger when the
// deployment routes that endpoint to KERMT and XGBoost answered it instead (ADR-033, ADR-034 item 7).
// Derived here from the contract and /generations, never passed in as a style or a flag. Provenance only:
// nothing about it is coloured, ranked or called better.
import { useGenerations } from "../data/useGenerations";
import { FALLBACK_NOTE, familyLabel, servedByFallback } from "../domain/modelFamily";
import type { EndpointPrediction } from "../types/contracts";

export function ModelSource({
  prediction,
  className,
}: {
  prediction: Pick<EndpointPrediction, "endpoint" | "model_id"> | undefined;
  className?: string;
}) {
  const kermtEndpoints = useGenerations()?.kermt_endpoints ?? [];
  if (!prediction) return null;
  const label = familyLabel(prediction.model_id);
  const fellBack = servedByFallback(prediction, kermtEndpoints);
  if (!label && !fellBack) return null;
  return (
    <span className={className}>
      {label}
      {fellBack && (
        <>
          <span aria-hidden="true"> †</span>
          <span className="sr-only"> ({FALLBACK_NOTE})</span>
        </>
      )}
    </span>
  );
}
