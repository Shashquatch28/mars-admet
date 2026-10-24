// The ADMET letters strip on the landing page, derived from the roster so its counts can never drift from
// the product's. The rule-based synthetic-accessibility score is not an ML endpoint and has no letter.
import {
  DISPLAY_GROUP_LABEL,
  DISPLAY_GROUP_ORDER,
  ML_ENDPOINTS,
  SHORT_LABEL,
  displayGroupOf,
  type DisplayGroup,
} from "../domain/endpoints";

export interface AdmetColumn {
  group: DisplayGroup;
  label: string;
  count: number;
  /** Conventional short names of the endpoints in this group, in roster order. */
  short: string;
}

export const ADMET: AdmetColumn[] = DISPLAY_GROUP_ORDER.filter((g) => g !== "rule-based").map((g) => {
  const members = ML_ENDPOINTS.filter((e) => displayGroupOf(e) === g);
  return {
    group: g,
    label: DISPLAY_GROUP_LABEL[g],
    count: members.length,
    short: members.map((e) => SHORT_LABEL[e]).join(", "),
  };
});
