// Structure-panel state logic, against the REAL conformer capture
// (src/domain/real-responses/, see its README).
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ConformerResponse, PredictionResponse } from "../types/contracts";
import { conformerCaption, conformerView } from "./conformer";

import conformer from "./real-responses/celecoxib-3d.json";
import miss from "./real-responses/celecoxib-miss.json";
import unknown404 from "./real-responses/unknown-molecule-404.json";

const C = conformer as unknown as ConformerResponse;
const P = miss as unknown as PredictionResponse;

describe("real conformer response", () => {
  it("belongs to the molecule the prediction was about", () => {
    expect(C.molecule_id).toBe(P.molecule_id);
  });

  it("carries explicit hydrogens and consistent atom/bond counts with its SDF block", () => {
    expect(C.atoms.some((a) => a.element === "H")).toBe(true);
    const counts = C.sdf_block.split("\n")[3].trim().split(/\s+/);
    expect(Number(counts[0])).toBe(C.atoms.length);
    expect(Number(counts[1])).toBe(C.bonds.length);
  });

  it("has only bonds between atoms that exist", () => {
    for (const b of C.bonds) {
      expect(b.atom_index_1).toBeGreaterThanOrEqual(0);
      expect(b.atom_index_2).toBeLessThan(C.atoms.length);
    }
  });

  it("caption states the real MMFF94 energy, not a literal", () => {
    expect(conformerCaption(C)).toBe(`ETKDG · MMFF94 · ${C.energy_kcal_mol.toFixed(1)} kcal/mol`);
    expect(conformerCaption({ ...C, energy_kcal_mol: -42.84 })).toBe("ETKDG · MMFF94 · −42.8 kcal/mol");
  });
});

describe("conformerView", () => {
  const base = { moleculeId: P.molecule_id, isPending: false, data: undefined, error: null };

  it("is idle with no molecule", () => {
    expect(conformerView({ ...base, moleculeId: null, isPending: true }).kind).toBe("idle");
    expect(conformerView({ ...base, moleculeId: "" }).kind).toBe("idle");
  });
  it("is loading while the request is pending", () => {
    expect(conformerView({ ...base, isPending: true }).kind).toBe("loading");
  });
  it("is ready with a caption once data arrives", () => {
    const v = conformerView({ ...base, data: C });
    expect(v).toEqual({ kind: "ready", caption: conformerCaption(C) });
  });
  it("treats 404 as unavailable (a normal state) and 501 as unsupported", () => {
    expect(conformerView({ ...base, error: { status: 404, message: unknown404.detail } }).kind).toBe("unavailable");
    expect(conformerView({ ...base, error: { status: 501, message: "no rdkit" } }).kind).toBe("unsupported");
  });
  it("any other failure is an error carrying its message", () => {
    expect(conformerView({ ...base, error: { status: 500, message: "boom" } })).toEqual({ kind: "error", message: "boom" });
    expect(conformerView({ ...base, error: { status: 0, message: "API unreachable" } })).toEqual({
      kind: "error",
      message: "API unreachable",
    });
  });
});

describe("fetchConformer", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.resetModules();
  });
  async function client(res: () => Response) {
    vi.stubEnv("VITE_API_BASE", "/api");
    const fetchMock = vi.fn(() => Promise.resolve(res()));
    vi.stubGlobal("fetch", fetchMock);
    vi.resetModules();
    return { ...(await import("../data/client")), fetchMock };
  }
  const json = (status: number, body: unknown) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

  it("requests /molecule/{id}/3d and returns the body", async () => {
    const { fetchConformer, fetchMock } = await client(() => json(200, conformer));
    await expect(fetchConformer(P.molecule_id)).resolves.toEqual(C);
    expect((fetchMock.mock.calls[0] as unknown as [string])[0]).toBe(`/api/molecule/${P.molecule_id}/3d`);
  });

  it("the real 404 body becomes ApiError(404) with the service's message, which maps to 'unavailable'", async () => {
    const { fetchConformer } = await client(() => json(404, unknown404));
    const err = await fetchConformer("0000000000000000").catch((e: unknown) => e);
    expect(err).toMatchObject({ status: 404, message: unknown404.detail });
    expect(conformerView({ moleculeId: "x", isPending: false, error: err as { status: number; message: string } }).kind).toBe(
      "unavailable",
    );
  });

  it("a 501 (written from api/app/routers/molecule.py; not captured, the test API has RDKit)", async () => {
    const { fetchConformer } = await client(() =>
      json(501, { detail: "Conformer generation needs rdkit, which is not installed in this environment" }),
    );
    await expect(fetchConformer("x")).rejects.toMatchObject({ status: 501 });
  });
});
