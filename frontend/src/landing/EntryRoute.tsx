// "/": the landing page on a first visit, Predict after that (ADR-046). Read once on mount, so marking the
// landing seen while it is on screen does not redirect the page out from under the person using it.
import { useState } from "react";
import { Navigate } from "react-router-dom";
import { LandingPage } from "./LandingPage";
import { entryTarget, hasSeenLanding } from "./entry";

export function EntryRoute() {
  const [seen] = useState(hasSeenLanding);
  return entryTarget(seen) === "predict" ? <Navigate to="/predict" replace /> : <LandingPage />;
}
