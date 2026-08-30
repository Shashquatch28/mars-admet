# MARS — TDC acquisition report

- **acq_id:** `20260830T181633Z`
- **acquired (UTC):** 2026-08-30T18:17:50.792502Z
- **PyTDC version:** `1.1.15`
- **Python:** `3.12.3 (main, Mar 23 2026, 19:04:32) [GCC 13.3.0]`
- **Platform:** `Linux-6.6.87.2-microsoft-standard-WSL2-x86_64-with-glibc2.39`
- **Repo git SHA:** `daddcf7cddff04d9c19d949b7a3dfec9b39fec9e` (dirty=None)
- **Acq env lockfile:** `ml/data/requirements-acquire.lock.txt` (sha256 `418ffe5afb0e2540…`)

Raw data under `ml/data/raw/<TDC_name>/<acq_id>/` is immutable. Snapshot hashes are order-independent content digests over `(Drug, Y)`.

| endpoint | dataset_key | TDC name | variant | task | N | ~N (blueprint) | in TDC benchmark | bench train_val/test | snapshot_sha256 (12) |
|---|---|---|---|---|--:|--:|:--:|--:|---|
| solubility_logs | `solubility_logs` | Solubility_AqSolDB | primary | regression | 9982 | 9982 | yes | 7985/1997 | `b2c129236536` |
| lipophilicity_logp | `lipophilicity_logp` | Lipophilicity_AstraZeneca | primary | regression | 4200 | 4200 | yes | 3360/840 | `81a1fdd397fb` |
| caco2_permeability | `caco2_permeability` | Caco2_Wang | primary | regression | 910 | 906 | yes | 728/182 | `b016af763204` |
| hia_absorption | `hia_absorption` | HIA_Hou | primary | classification | 578 | 578 | yes | 461/117 | `8cd1a2d974b1` |
| pgp_inhibition | `pgp_inhibition` | Pgp_Broccatelli | primary | classification | 1218 | 1212 | yes | 973/245 | `f4884462e0b4` |
| bbb_permeability | `bbb_permeability` | BBB_Martins | primary | classification | 2030 | 1975 | yes | 1624/406 | `4f7bedbfd56b` |
| ppb_binding | `ppb_binding` | PPBR_AZ | primary | regression | 1614 | 1797 | yes | 2231/559 | `dd7c82095a7c` |
| cyp3a4_inhibition | `cyp3a4_inhibition` | CYP3A4_Veith | primary | classification | 12328 | 12328 | yes | 9861/2467 | `ce1a8df21cb9` |
| cyp2d6_inhibition | `cyp2d6_inhibition` | CYP2D6_Veith | primary | classification | 13130 | 13130 | yes | 10504/2626 | `3aaa7087af6c` |
| cyp2c9_inhibition | `cyp2c9_inhibition` | CYP2C9_Veith | primary | classification | 12092 | 12092 | yes | 9673/2419 | `4e88221e570f` |
| clearance_microsomal | `clearance_microsomal` | Clearance_Microsome_AZ | primary | regression | 1102 | 1102 | yes | 881/221 | `b89ccefd0504` |
| herg_cardiotoxicity | `herg_cardiotoxicity` | hERG_Karim | primary | classification | 13445 | 13445 | no | — | `dfd70f76ff6b` |
| herg_cardiotoxicity | `herg_cardiotoxicity__benchmark` | hERG | benchmark_alt | classification | 655 | 655 | yes | 523/132 | `9280a5d5029a` |
| ames_mutagenicity | `ames_mutagenicity` | AMES | primary | classification | 7278 | 7255 | yes | 5821/1457 | `1d20ccdb251e` |
| dili_liver_injury | `dili_liver_injury` | DILI | primary | classification | 475 | 475 | yes | 379/96 | `47347250091d` |

## Notes

- **herg:** Two hERG datasets acquired: 'hERG_Karim' (primary, ~13445, blueprint Module 2) and 'hERG' (benchmark_alt, ~655, TDC ADMET Benchmark Group). endpoint->dataset choice for herg_cardiotoxicity is deferred to Run 2 EDA (decision 2026-08-30). See documentation/FUTURE_SCOPE.md.
- **dilist:** DILIst augmentation source (Module 1 §6) is not a TDC dataset; its acquisition + provenance is deferred to Run 2.
- **hERG_Karim_not_leaderboard_comparable:** hERG_Karim is absent from TDC's ADMET Benchmark Group; the published TDC hERG leaderboard is computed on the 655-compound 'hERG'. Results on hERG_Karim are not directly leaderboard-comparable (blueprint Module 1 §4 wording flagged for the maintainer).
