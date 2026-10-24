// Whether this browser has already been through the landing page (ADR-046). The landing is the front door
// at "/" for a first visit only; after that "/" goes straight to Predict, as it did before the landing
// existed. "/welcome" always shows it. Remembered in this browser only; storage can be blocked, in which
// case "/" simply shows the landing each time.
import { readFlag, writeFlag } from "../app/persistedFlag";

export const SEEN_LANDING_KEY = "mars.seenLanding";

export const hasSeenLanding = (): boolean => readFlag(SEEN_LANDING_KEY);
export const markLandingSeen = (): void => writeFlag(SEEN_LANDING_KEY, true);

/** The one molecule the landing offers as an example. It is an input only: what the page shows for it is
 *  whatever the service returns for it (ADR-032), never a value written into the page. */
export const EXAMPLE_SMILES = "CC(=O)Nc1ccc(O)cc1";

/** Where "/" goes: the landing on a first visit, Predict after that. */
export function entryTarget(seen: boolean): "landing" | "predict" {
  return seen ? "predict" : "landing";
}
