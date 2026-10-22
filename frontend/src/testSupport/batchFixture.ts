// Test-only: a deterministic 240-molecule batch response. Illustrative values, NOT model output.
// Nothing under src outside this folder and *.test.ts may import it (tests/noHardcodedGuard.test.ts).
import type { BatchPredictResponse, Endpoint, EndpointPrediction } from "../types/contracts";
import { STUB_MODEL_ID, ALL_ENDPOINTS } from "../domain/endpoints";

// --- fixture -----------------------------------------------------------------
// Illustrative only. Deterministic (seeded, no Math.random) so values are stable
// across renders — a virtualized grid that re-randomised on scroll would be
// unusable, and unstable fixtures hide real bugs.

const POOL: [string, string][] = [
  ["CC(=O)Oc1ccccc1C(=O)O", "aspirin"],
  ["CN1C=NC2=C1C(=O)N(C)C(=O)N2C", "caffeine"],
  ["CC(C)Cc1ccc(C(C)C(=O)O)cc1", "ibuprofen"],
  ["CC(=O)Nc1ccc(O)cc1", "paracetamol"],
  ["CC1=CC=C(C=C1)C1=CC(=NN1C1=CC=C(C=C1)S(N)(=O)=O)C(F)(F)F", "celecoxib"],
  ["CC(C)NCC(O)COc1ccccc1OCC=C", "oxprenolol"],
  ["Clc1ccccc1C1=NCC(=O)Nc2ccc(Cl)cc21", "lorazepam-like"],
  ["COc1ccc2cc(ccc2c1)C(C)C(=O)O", "naproxen"],
  ["CN(C)CCCN1c2ccccc2Sc2ccc(Cl)cc21", "chlorpromazine"],
  ["OC(=O)C1=CC=CC=C1O", "salicylic acid"],
  ["CCN(CC)CCNC(=O)c1cc(Cl)c(N)cc1OC", "metoclopramide"],
  ["CC(C)(C)NCC(O)c1ccc(O)c(CO)c1", "salbutamol"],
];

function lcg(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

const REG_RANGE: Partial<Record<Endpoint, [number, number]>> = {
  solubility_logs: [-6.5, -0.5],
  lipophilicity_logp: [-0.5, 5.5],
  caco2_permeability: [-6.5, -4.2],
  ppb_binding: [55, 99.5],
  clearance_microsomal: [2, 60],
  synthetic_accessibility: [1.4, 5.2],
};

export function makeBatchFixture(n = 240, seed = 20261006): BatchPredictResponse {
  const rnd = lcg(seed);
  const results = [];

  for (let i = 0; i < n; i++) {
    const [smiles, name] = POOL[i % POOL.length];
    const id = (0x1000000 + Math.floor(rnd() * 0xeffffff)).toString(16).padStart(8, "0");

    // ~3% of rows fail validation before inference — a real, non-blocking
    // per-row error (BatchRowResult.error), not an empty row.
    if (rnd() < 0.03) {
      results.push({
        row_index: i,
        smiles_input: smiles.slice(0, Math.max(6, Math.floor(smiles.length * 0.6))),
        ok: false,
        error: "unclosed ring bond at position 14",
        prediction: null,
      });
      continue;
    }

    const oodProne = rnd() < 0.14;
    const dropClearance = rnd() < 0.18;
    const predictions: EndpointPrediction[] = [];

    for (const e of ALL_ENDPOINTS) {
      if (e === "clearance_microsomal" && dropClearance) continue;

      const range = REG_RANGE[e];
      const isReg = !!range;
      const base = isReg ? range[0] + rnd() * (range[1] - range[0]) : rnd();
      const value = isReg ? Math.round(base * 100) / 100 : Math.round(base * 100) / 100;
      const spread = isReg ? (range[1] - range[0]) * 0.06 : 0.07;
      const stub = e === "cyp2c9_inhibition";
      const inDomain = stub ? true : !(oodProne && rnd() < 0.45);

      predictions.push({
        endpoint: e,
        value,
        unit: isReg ? null : null,
        confidence_low: Math.round((value - spread) * 100) / 100,
        confidence_high: Math.round((value + spread) * 100) / 100,
        in_domain: inDomain,
        knn_distance: Math.round((inDomain ? 0.2 + rnd() * 0.3 : 0.6 + rnd() * 0.3) * 100) / 100,
        model_id: stub ? STUB_MODEL_ID : "mars-xgboost-ecfp-v1",
        ad_threshold: stub ? null : 0.58,
      });
    }

    results.push({
      row_index: i,
      smiles_input: smiles,
      ok: true,
      error: null,
      prediction: {
        smiles_input: smiles,
        smiles_standardized: smiles,
        molecule_id: `${id}${name.length.toString(16)}${(i % 16).toString(16)}`.slice(0, 16),
        predictions,
        model_version: "mars-routing@v0.3.1",
        served_at: "2026-10-06T09:12:44Z",
        cache_hit: false,
      },
    });
  }

  return { job_id: "job_7f2a19c4", status: "done", total: n, completed: n, results };
}
