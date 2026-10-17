# Held-out-error band, regression endpoints

Level 90%. The half-width is fixed from the pooled out-of-fold residuals only; the test columns
report how often it held on the held-out test molecules and played no part in choosing it.
The band is one constant per endpoint (marginal, not per-molecule) and it under-covers
out-of-domain molecules, which is why the applicability-domain flag stays beside it.

| Endpoint | half-width | pooled residuals | test n | test cover | in-domain | out-of-domain (n) |
|---|---|---|---|---|---|---|
| solubility_logs | 1.677 | 4700 | 1960 | 0.90 | 0.91 | 0.86 (518) |
| lipophilicity_logp | 1.103 | 2100 | 840 | 0.90 | 0.92 | 0.80 (105) |
| caco2_permeability | 0.615 | 450 | 180 | 0.93 | 0.92 | 0.93 (61) |
| ppb_binding | 18.07 | 805 | 323 | 0.87 | 0.88 | 0.43 (7) |
| clearance_microsomal | 51.21 | 550 | 221 | 0.86 | 0.87 | 0.80 (20) |

Regenerate: `cd ml && PYTHONPATH=. python train/build_error_bands.py --report <path>`.
