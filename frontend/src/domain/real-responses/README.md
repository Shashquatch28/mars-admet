# Real API responses

Raw bodies captured from the running MARS API on **2026-10-07**, unedited. They
exist so tests can check what the service *actually* sends rather than what we
assumed it would (`../realResponses.test.ts`). Do not hand-edit them; re-capture.

| File | How it was captured |
|---|---|
| `celecoxib-miss.json` | `POST /predict` `{smiles: <celecoxib>}`, real-model path (promoted models + rule-based SA), first call (`cache_hit: false`) |
| `celecoxib-hit.json` | the identical request again (`cache_hit: true`) |
| `celecoxib-subset.json` | `endpoints: [solubility_logs, herg_cardiotoxicity, synthetic_accessibility]` |
| `celecoxib-stub-only.json` | same request against an API container **without** the ml stack (every row `stub-v0`) |
| `invalid-smiles-422.json` | `{smiles: "not_a_smiles(("}` — `detail` is a string |
| `empty-422.json` | `{smiles: "  "}` — `detail` is a string |
| `missing-field-422.json` | `{}` — `detail` is a list of validation errors |

## Provenance caveats

- The real-model responses came from a **scratch image** built from the repo's
  `api/Dockerfile` plus `greenlet` (a fresh `docker build` of the unmodified
  Dockerfile failed at the time: `sqlalchemy>=2.0` without the `[asyncio]` extra),
  run against the repo's `ml/artifacts`. Request/response code is the checked-in
  `api/app` and `ml/serve`.
- The stub-only response came from the older `mars_api` image, whose `ml/serve`
  predates `rule_based.py`, so it has no SA row.
- These molecules' *values* are model output and may change when artifacts are
  re-promoted. Tests therefore assert structure and invariants, not numbers.

## Facts these captures established (versus the hand-written fixture)

- `unit` is `null` on every model row; only the SA row carries one (`"SA score"`).
- A top-level `model_version` of `"stub-v0"` is returned even when every row was
  served by a real model (backend: `_route_to_models` does not update it).
- `smiles_input` is returned already standardized, not as submitted.
- A cache hit returns the original `served_at`.
- Celecoxib is out of domain on 5 of 14 endpoints (the design fixture had 2).
