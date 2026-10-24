// The hook's states, rendered on the server so no effect runs: a held answer is shown at once, and nothing is asked for a
// structure that has only just appeared (ADR-044). The visible words for each state are what a person reads.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type * as HookModule from "./useMoleculeName";
import type * as NameComponent from "../components/MoleculeName";
import type { NameResponse } from "../types/contracts";

const FOUND: NameResponse = {
  status: "found",
  inchikey: "K",
  source: "PubChem",
  source_record: "CID 2244",
  source_url: "https://pubchem.ncbi.nlm.nih.gov/compound/2244",
  preferred_name: "Aspirin",
  iupac_name: "2-acetyloxybenzoic acid",
  synonyms: ["Acylpyrin"],
  reason: null,
};

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

async function html(smiles: string | null, held?: NameResponse, variant: "line" | "block" = "line") {
  vi.resetModules();
  vi.stubEnv("VITE_API_BASE", "/api");
  const { nameKey } = (await import("./useMoleculeName")) as typeof HookModule;
  const { LookedUpName } = (await import("../components/MoleculeName")) as typeof NameComponent;
  const qc = new QueryClient();
  if (held && smiles) qc.setQueryData(nameKey(smiles.trim()), held);
  return renderToString(
    <QueryClientProvider client={qc}>
      <LookedUpName smiles={smiles} variant={variant} disclose />
    </QueryClientProvider>,
  );
}

describe("LookedUpName", () => {
  it("renders nothing, and asks nobody, with no structure", async () => {
    expect(await html(null)).toBe("");
    expect(await html("   ")).toBe("");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("says it is looking for a structure that has only just appeared, and has asked nobody yet", async () => {
    const out = await html("CCO");
    expect(out).toContain("Looking up the name");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows a held name at once, with its source and what was sent", async () => {
    const out = await html("CCO", FOUND);
    expect(out).toContain("Aspirin");
    expect(out).toContain("PubChem, CID 2244");
    expect(out).toContain("The SMILES is not sent");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows 'No name found' for a held no-match, in words, and not as an error", async () => {
    const out = await html("CCO", { ...FOUND, status: "not_found", preferred_name: null, iupac_name: null, synonyms: [], source_record: null });
    expect(out).toContain("No name found");
    expect(out).toContain("PubChem has no record of this structure");
    expect(out).not.toMatch(/error|failed/i);
  });

  it("shows 'Name unavailable' and why for a held source failure", async () => {
    const out = await html("CCO", { ...FOUND, status: "unavailable", preferred_name: null, reason: "PubChem did not answer within 4 s" });
    expect(out).toContain("Name unavailable");
    expect(out).toContain("PubChem did not answer within 4 s");
  });

  it("the block shows the IUPAC name, the synonyms, the record link and the full statement of what was sent", async () => {
    const out = await html("CCO", FOUND, "block");
    expect(out).toContain("2-acetyloxybenzoic acid");
    expect(out).toContain("Acylpyrin");
    expect(out).toContain('href="https://pubchem.ncbi.nlm.nih.gov/compound/2244"');
    expect(out).toContain("noopener");
    expect(out).toContain("InChIKey");
  });

  it("asks nobody when there is no API, even for a structure", async () => {
    vi.resetModules();
    vi.stubEnv("VITE_API_BASE", "");
    const { LookedUpName } = (await import("../components/MoleculeName")) as typeof NameComponent;
    const out = renderToString(
      <QueryClientProvider client={new QueryClient()}>
        <LookedUpName smiles="CCO" />
      </QueryClientProvider>,
    );
    expect(out).toBe("");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
