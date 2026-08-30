# MARS — M1 EDA report

- **eda_id:** `20260830T191149Z`
- **generated:** 2026-08-30T19:13:59.339352Z
- **standardizer:** `mars-standardizer-v1`
- **acquisition:** `20260830T181633Z` (PyTDC 1.1.15)

Every dataset in the acquisition lockfile was standardized with the Module 3 Stage 1 pipeline. Numbers below are computed over standardized molecules with parseable labels.

| dataset | task | raw | valid | valid% | uniq mol | dup% | multi-meas | conflicts | conflict%(of multi) | stereo-def% | uniq scaff | top scaff% |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| `ames_mutagenicity` (primary) | classification | 7278 | 7278 | 100.0% | 7255 | 0.3% | 23 | 0 | 0.0% | 14.0% | 1577 | 17.4% |
| `bbb_permeability` (primary) | classification | 2030 | 2030 | 100.0% | 1966 | 3.2% | 60 | 11 | 18.3% | 35.3% | 1020 | 6.6% |
| `caco2_permeability` (primary) | regression | 910 | 910 | 100.0% | 904 | 0.7% | 6 | 4 | 66.7% | 54.1% | 450 | 5.1% |
| `clearance_microsomal` (primary) | regression | 1102 | 1102 | 100.0% | 1102 | 0.0% | 0 | 0 | 0.0% | 34.2% | 711 | 2.9% |
| `cyp2c9_inhibition` (primary) | classification | 12092 | 12092 | 100.0% | 12051 | 0.3% | 37 | 6 | 16.2% | 30.5% | 7098 | 4.0% |
| `cyp2d6_inhibition` (primary) | classification | 13130 | 13130 | 100.0% | 13090 | 0.3% | 37 | 5 | 13.5% | 29.1% | 7728 | 4.0% |
| `cyp3a4_inhibition` (primary) | classification | 12328 | 12328 | 100.0% | 12296 | 0.3% | 31 | 1 | 3.2% | 29.0% | 7379 | 4.2% |
| `dili_liver_injury` (primary) | classification | 475 | 475 | 100.0% | 474 | 0.2% | 1 | 0 | 0.0% | 0.0% | 310 | 11.4% |
| `herg_cardiotoxicity` (primary) | classification | 13445 | 13445 | 100.0% | 13152 | 2.2% | 285 | 16 | 5.6% | 41.0% | 5922 | 0.9% |
| `herg_cardiotoxicity__benchmark` (benchmark_alt) | classification | 655 | 655 | 100.0% | 616 | 6.0% | 39 | 9 | 23.1% | 54.8% | 370 | 5.0% |
| `hia_absorption` (primary) | classification | 578 | 578 | 100.0% | 578 | 0.0% | 0 | 0 | 0.0% | 58.3% | 385 | 11.1% |
| `lipophilicity_logp` (primary) | regression | 4200 | 4200 | 100.0% | 4200 | 0.0% | 0 | 0 | 0.0% | 28.2% | 2408 | 1.8% |
| `pgp_inhibition` (primary) | classification | 1218 | 1218 | 100.0% | 1212 | 0.5% | 6 | 0 | 0.0% | 54.1% | 682 | 5.4% |
| `ppb_binding` (primary) | regression | 1614 | 1614 | 100.0% | 1614 | 0.0% | 0 | 0 | 0.0% | 36.0% | 1032 | 2.0% |
| `solubility_logs` (primary) | regression | 9982 | 9980 | 100.0% | 9478 | 5.0% | 232 | 218 | 94.0% | 9.8% | 1883 | 27.1% |

## Per-endpoint distributions

### `ames_mutagenicity` (primary, classification)
- class balance: counts={'0': 3304, '1': 3974} | positive fraction 54.6%

### `bbb_permeability` (primary, classification)
- class balance: counts={'0': 479, '1': 1551} | positive fraction 76.4%
- **stereo-flagged endpoint (Module 3):** stereo-defined ratio = 35.3%

### `caco2_permeability` (primary, regression)
- Y: n=910 min=-7.76 p25=-5.78 med=-5.13 p75=-4.64 max=-3.51 mean=-5.24 std=0.777
- **stereo-flagged endpoint (Module 3):** stereo-defined ratio = 54.1%

### `clearance_microsomal` (primary, regression)
- Y: n=1102 min=3 p25=3 med=12.9 p75=42.7 max=150 mean=34.2 std=44.8

### `cyp2c9_inhibition` (primary, classification)
- class balance: counts={'0': 8047, '1': 4045} | positive fraction 33.5%
- **stereo-flagged endpoint (Module 3):** stereo-defined ratio = 30.5%

### `cyp2d6_inhibition` (primary, classification)
- class balance: counts={'0': 10616, '1': 2514} | positive fraction 19.1%
- **stereo-flagged endpoint (Module 3):** stereo-defined ratio = 29.1%

### `cyp3a4_inhibition` (primary, classification)
- class balance: counts={'0': 7218, '1': 5110} | positive fraction 41.5%
- **stereo-flagged endpoint (Module 3):** stereo-defined ratio = 29.0%

### `dili_liver_injury` (primary, classification)
- class balance: counts={'0': 239, '1': 236} | positive fraction 49.7%

### `herg_cardiotoxicity` (primary, classification)
- class balance: counts={'0': 6727, '1': 6718} | positive fraction 50.0%

### `herg_cardiotoxicity__benchmark` (benchmark_alt, classification)
- class balance: counts={'0': 204, '1': 451} | positive fraction 68.9%

### `hia_absorption` (primary, classification)
- class balance: counts={'0': 78, '1': 500} | positive fraction 86.5%

### `lipophilicity_logp` (primary, regression)
- Y: n=4200 min=-1.5 p25=1.41 med=2.36 p75=3.1 max=4.5 mean=2.19 std=1.2

### `pgp_inhibition` (primary, classification)
- class balance: counts={'0': 568, '1': 650} | positive fraction 53.4%
- **stereo-flagged endpoint (Module 3):** stereo-defined ratio = 54.1%

### `ppb_binding` (primary, regression)
- Y: n=1614 min=11.2 p25=85.2 med=95.4 p75=98.6 max=100 mean=88.1 std=16.7

### `solubility_logs` (primary, regression)
- Y: n=9980 min=-13.2 p25=-4.33 med=-2.62 p75=-1.21 max=2.14 mean=-2.89 std=2.37
- rejections: {'sanitize-failed': 2}
