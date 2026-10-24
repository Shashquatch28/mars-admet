// A molecule's name as MARS shows it (ADR-044). Pure and tested.
//
// A name is only ever what a name source returned for the structure's InChIKey, shown with that source, or what the user typed.
// It is never made up from a SMILES, and it says nothing about a prediction: it is not an endpoint, a value or a judgement, so
// nothing here colours, ranks or marks anything. "No name found" is an answer; "unavailable" is a failure, and the two are never
// confused: a failure is not evidence that a molecule has no name.
import type { NameResponse } from "../types/contracts";

/** What the interface tells people about what leaves the server, wherever a looked-up name is explained in full. */
export const NAME_DISCLOSURE =
  "MARS asks PubChem for this name using the structure's InChIKey, a fixed identifier computed from the structure. The SMILES itself is not sent, and PubChem is told nothing about you.";

/** The same statement in one line, for a place with room for little else. */
export const NAME_DISCLOSURE_SHORT = "Asked using the structure's InChIKey. The SMILES is not sent.";

export type NameView =
  | { kind: "idle" }
  | { kind: "looking" }
  | {
      kind: "found";
      /** The source's preferred title; null when the record has none (it is then said so, not filled in). */
      name: string | null;
      iupac: string | null;
      synonyms: string[];
      /** "PubChem, CID 2244" */
      source: string;
      url: string | null;
    }
  | { kind: "none"; source: string }
  | { kind: "unavailable"; reason: string };

/** "PubChem, CID 2244": who said it, and which of its records. */
export function sourceLine(r: Pick<NameResponse, "source" | "source_record">): string {
  return r.source_record ? `${r.source}, ${r.source_record}` : r.source;
}

/** Why a name was not looked up when the request itself failed, in words. None is about the molecule. */
export function nameFailure(status: number, message: string): string {
  if (status === 501) return "This server cannot work out the identifier PubChem is asked about, so no name is looked up.";
  if (status === 422) return `The structure could not be turned into an identifier: ${message.replace(/\.$/, "")}.`;
  if (status === 429) return "Too many names were asked for in the last minute. MARS will ask again when this molecule is shown next.";
  if (status === 0) return "The API is unreachable, so no name was looked up.";
  return `The name lookup failed (${status}).`;
}

export function nameView(input: {
  /** There is a structure to name and an API to ask. */
  hasStructure: boolean;
  pending: boolean;
  data?: NameResponse | null;
  error?: { status: number; message: string } | null;
}): NameView {
  if (!input.hasStructure) return { kind: "idle" };
  if (input.error) return { kind: "unavailable", reason: nameFailure(input.error.status, input.error.message) };
  const d = input.data;
  if (!d) return input.pending ? { kind: "looking" } : { kind: "idle" };
  if (d.status === "found") {
    return {
      kind: "found",
      name: d.preferred_name,
      iupac: d.iupac_name,
      synonyms: d.synonyms,
      source: sourceLine(d),
      url: d.source_url,
    };
  }
  if (d.status === "not_found") return { kind: "none", source: d.source };
  return { kind: "unavailable", reason: d.reason ?? `${d.source} did not answer.` };
}

export interface HeadlineName {
  text: string;
  /** Shown beside the name: "typed by you" or the source line. */
  source: string;
  origin: "typed" | "looked_up";
}

/**
 * The one name a header shows for a molecule: what the user typed, else what the source returned, else null (the caller then
 * writes "Molecule N"). A typed name always wins and is never overwritten, and a failure or "no name found" never produces one.
 */
export function headlineName(typed: string | null | undefined, view: NameView): HeadlineName | null {
  const t = (typed ?? "").trim();
  if (t) return { text: t, source: "typed by you", origin: "typed" };
  if (view.kind === "found" && view.name) return { text: view.name, source: view.source, origin: "looked_up" };
  return null;
}

/** Whether to ask now: a structure that has stayed on screen, or one whose answer is already held. */
export function shouldAsk(input: { hasStructure: boolean; settled: boolean; known: boolean }): boolean {
  return input.hasStructure && (input.known || input.settled);
}
