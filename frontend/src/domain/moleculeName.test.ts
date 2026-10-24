// A molecule's name as MARS shows it (ADR-044): the five states, the precedence of names, and what the copy may say.
import { describe, expect, it } from "vitest";
import { NAME_DISCLOSURE, NAME_DISCLOSURE_SHORT, headlineName, nameFailure, nameView, shouldAsk, sourceLine } from "./moleculeName";
import { NAME_STATEMENT, buildReport, reportNameRows } from "./report";
import type { NameResponse, PredictionResponse } from "../types/contracts";
import type { ExportMolecule } from "./exportCsv";
import { reconcile, requestedMlEndpoints } from "./reconcile";
import miss from "./real-responses/celecoxib-miss.json";

const MISS = miss as PredictionResponse;

const FOUND: NameResponse = {
  status: "found",
  inchikey: "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
  source: "PubChem",
  source_record: "CID 2244",
  source_url: "https://pubchem.ncbi.nlm.nih.gov/compound/2244",
  preferred_name: "Aspirin",
  iupac_name: "2-acetyloxybenzoic acid",
  synonyms: ["Acetylsalicylic acid", "Acylpyrin"],
  reason: null,
};
const NONE: NameResponse = {
  ...FOUND,
  status: "not_found",
  source_record: null,
  source_url: null,
  preferred_name: null,
  iupac_name: null,
  synonyms: [],
};
const DOWN: NameResponse = { ...NONE, status: "unavailable", reason: "PubChem did not answer within 4 s; the molecule is not named for now" };

const view = (data?: NameResponse | null, extra: Partial<Parameters<typeof nameView>[0]> = {}) =>
  nameView({ hasStructure: true, pending: false, data, ...extra });

describe("the five states", () => {
  it("is idle with no structure to name, whatever else is true", () => {
    expect(nameView({ hasStructure: false, pending: true, data: FOUND })).toEqual({ kind: "idle" });
  });
  it("is looking while the answer is awaited", () => {
    expect(view(undefined, { pending: true })).toEqual({ kind: "looking" });
  });
  it("is found, with the name, the IUPAC name, the synonyms and the source in words", () => {
    expect(view(FOUND)).toEqual({
      kind: "found",
      name: "Aspirin",
      iupac: "2-acetyloxybenzoic acid",
      synonyms: ["Acetylsalicylic acid", "Acylpyrin"],
      source: "PubChem, CID 2244",
      url: "https://pubchem.ncbi.nlm.nih.gov/compound/2244",
    });
  });
  it("keeps 'a record with no title' as found with no name, never fills one in", () => {
    expect(view({ ...FOUND, preferred_name: null })).toMatchObject({ kind: "found", name: null });
  });
  it("is 'none' for no match, with the source: an answer, not a failure", () => {
    expect(view(NONE)).toEqual({ kind: "none", source: "PubChem" });
  });
  it("is unavailable, with the service's reason, when the source failed", () => {
    expect(view(DOWN)).toEqual({ kind: "unavailable", reason: DOWN.reason });
  });
  it("is unavailable, in words, when the request itself failed, and never 'none'", () => {
    for (const [status, words] of [
      [0, "unreachable"],
      [429, "Too many"],
      [501, "cannot work out"],
      [422, "could not be turned into an identifier"],
      [500, "failed (500)"],
    ] as const) {
      const v = view(undefined, { error: { status, message: "m" } });
      expect(v.kind).toBe("unavailable");
      expect(v.kind === "unavailable" && v.reason).toContain(words);
    }
  });
  it("tells a failure apart from no match", () => {
    expect(view(DOWN).kind).not.toBe(view(NONE).kind);
  });
});

describe("source line", () => {
  it("names the source and its record", () => {
    expect(sourceLine(FOUND)).toBe("PubChem, CID 2244");
    expect(sourceLine({ source: "PubChem", source_record: null })).toBe("PubChem");
    expect(sourceLine({ source: "local database, version 2", source_record: "id 7" })).toBe("local database, version 2, id 7");
  });
});

describe("which name a header shows: typed, then looked up, then none", () => {
  const found = view(FOUND);
  it("a typed name wins over a looked-up one and says who gave it", () => {
    expect(headlineName("  My compound ", found)).toEqual({ text: "My compound", source: "typed by you", origin: "typed" });
  });
  it("without a typed name, the looked-up name is shown with its source", () => {
    expect(headlineName("", found)).toEqual({ text: "Aspirin", source: "PubChem, CID 2244", origin: "looked_up" });
    expect(headlineName(undefined, found)?.origin).toBe("looked_up");
    expect(headlineName("   ", found)?.origin).toBe("looked_up");
  });
  it("with neither, there is no name and the caller writes 'Molecule N'", () => {
    expect(headlineName("", { kind: "none", source: "PubChem" })).toBeNull();
    expect(headlineName("", { kind: "unavailable", reason: "x" })).toBeNull();
    expect(headlineName("", { kind: "looking" })).toBeNull();
    expect(headlineName("", { kind: "idle" })).toBeNull();
  });
  it("a record with no title gives no headline: the IUPAC name is not promoted to a name", () => {
    expect(headlineName("", view({ ...FOUND, preferred_name: null }))).toBeNull();
  });
  it("a typed name is kept even when the lookup failed or found nothing", () => {
    expect(headlineName("Mine", view(DOWN))?.text).toBe("Mine");
    expect(headlineName("Mine", view(NONE))?.text).toBe("Mine");
  });
});

describe("when to ask", () => {
  it("asks only for a structure that has stayed on screen, or whose answer is held", () => {
    expect(shouldAsk({ hasStructure: true, settled: false, known: false })).toBe(false);
    expect(shouldAsk({ hasStructure: true, settled: true, known: false })).toBe(true);
    expect(shouldAsk({ hasStructure: true, settled: false, known: true })).toBe(true);
    expect(shouldAsk({ hasStructure: false, settled: true, known: true })).toBe(false);
  });
});

describe("the words never claim more than the lookup is", () => {
  const banned = /\b(anonymous|anonymised|anonymized|private|safe|safety|good|bad|better|worse|risk|risky|toxic|favourable|favorable)\b/i;
  const copy = [
    NAME_DISCLOSURE,
    NAME_DISCLOSURE_SHORT,
    NAME_STATEMENT,
    nameFailure(0, ""),
    nameFailure(429, ""),
    nameFailure(501, ""),
    nameFailure(422, "x"),
    nameFailure(500, ""),
  ];
  it("says what is sent, and does not call it anonymous", () => {
    expect(NAME_DISCLOSURE).toContain("InChIKey");
    expect(NAME_DISCLOSURE).toContain("SMILES itself is not sent");
    expect(NAME_DISCLOSURE_SHORT).toContain("InChIKey");
    for (const t of copy) expect(t).not.toMatch(banned);
  });
});

describe("the printed report's name rows", () => {
  it("print the name, the IUPAC name and the synonyms, each with its source", () => {
    expect(reportNameRows(view(FOUND))).toEqual([
      { label: "Name", value: "Aspirin (PubChem, CID 2244)" },
      { label: "IUPAC name", value: "2-acetyloxybenzoic acid (PubChem, CID 2244)" },
      { label: "Also listed as", value: "Acetylsalicylic acid; Acylpyrin (PubChem, CID 2244)" },
    ]);
  });
  it("say 'no name found' and 'not included' in words", () => {
    expect(reportNameRows(view(NONE))?.[0].value).toBe("No name found (PubChem has no record of this structure)");
    expect(reportNameRows(view(DOWN))?.[0].value).toBe("Not included: PubChem did not answer within 4 s; the molecule is not named for now.");
  });
  it("print nothing when no lookup was attempted or finished", () => {
    expect(reportNameRows(null)).toBeNull();
    expect(reportNameRows({ kind: "idle" })).toBeNull();
    expect(reportNameRows({ kind: "looking" })).toBeNull();
  });
  it("a real molecule's report carries the name rows and the statement, and none when the lookup did not finish", () => {
    const m = { smilesInput: MISS.smiles_input, response: MISS, cells: reconcile(MISS, requestedMlEndpoints(null)).rows } as ExportMolecule;
    const named = buildReport(m, new Date("2026-10-19T12:00:00Z"), [], null, view(FOUND));
    expect(named.name?.[0]).toEqual({ label: "Name", value: "Aspirin (PubChem, CID 2244)" });
    expect(named.statements).toContain(NAME_STATEMENT);
    const unasked = buildReport(m, new Date("2026-10-19T12:00:00Z"), [], null, { kind: "looking" });
    expect(unasked.name).toBeNull();
    expect(unasked.statements).not.toContain(NAME_STATEMENT);
  });
  it("a molecule that failed before inference has no name rows and no statement", () => {
    const m = { smilesInput: "CCO", response: null, cells: [], error: "no result" } as never;
    const r = buildReport(m, new Date(), [], null, view(FOUND));
    expect(r.name).toBeNull();
    expect(r.statements).not.toContain(NAME_STATEMENT);
  });
});
