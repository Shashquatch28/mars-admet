# MARS beside the TDC ADMET leaderboard (Module 11 section 4)

Generated 2026-10-24 by `ml/eval/tdc_leaderboard_table.py`. Leaderboard values were read from the public TDC pages on 2026-10-24 (`tdc_leaderboard_reference.json`). MARS values are the production XGBoost, five seeds, test split, raw scores, no hyperparameter search.

**This table gives values. It does not say MARS is above or below the leaderboard**, and it should not be quoted that way: read the caveats below first.

| endpoint | TDC dataset | metric | MARS XGBoost | MARS served (KERMT-routed only) | MapLight | MapLight + GNN | CaliciBoost | top entry on the page (unaudited) | MARS n_test / TDC size |
|---|---|---|---|---|---|---|---|---|---|
| caco2_permeability | Caco2_Wang | MAE | 0.288 ± 0.012 | - | 0.276 ± 0.005 | 0.287 ± 0.005 | 0.256 ± 0.006 | CaliciBoost 0.256 ± 0.006 | 180 / 906 |
| hia_absorption | HIA_Hou | AUROC | 0.972 ± 0.002 | - | 0.986 ± 0.000 | 0.989 ± 0.001 | not listed | MiniMol 0.993 ± 0.005 | 117 / 578 |
| pgp_inhibition | Pgp_Broccatelli | AUROC | 0.910 ± 0.005 | 0.932 ± 0.004 | 0.930 ± 0.002 | 0.938 ± 0.002 | not listed | MapLight + GNN 0.938 ± 0.002 | 245 / 1212 |
| lipophilicity_logp | Lipophilicity_AstraZeneca | MAE | 0.544 ± 0.006 | 0.460 ± 0.014 | 0.539 ± 0.002 | 0.525 ± 0.003 | not listed | MiniMol 0.456 ± 0.008 | 840 / 4200 |
| solubility_logs | Solubility_AqSolDB | MAE | 0.810 ± 0.014 | - | 0.792 ± 0.002 | 0.789 ± 0.003 | not listed | MiniMol 0.741 ± 0.013 | 1960 / 9982 |
| bbb_permeability | BBB_Martins | AUROC | 0.901 ± 0.009 | 0.941 ± 0.003 | 0.916 ± 0.001 | 0.913 ± 0.001 | not listed | MiniMol 0.924 ± 0.003 | 394 / 1975 |
| cyp2c9_inhibition | CYP2C9_Veith | AUPRC | 0.790 ± 0.003 | - | 0.783 ± 0.002 | 0.859 ± 0.001 | not listed | MapLight + GNN 0.859 ± 0.001 | 2411 / 12092 |
| cyp2d6_inhibition | CYP2D6_Veith | AUPRC | 0.676 ± 0.006 | 0.688 ± 0.005 | 0.723 ± 0.003 | 0.790 ± 0.001 | not listed | MapLight + GNN 0.790 ± 0.001 | 2621 / 13130 |
| cyp3a4_inhibition | CYP3A4_Veith | AUPRC | 0.880 ± 0.001 | - | 0.881 ± 0.001 | 0.916 ± 0.000 | not listed | MapLight + GNN 0.916 ± 0.000 | 2463 / 12328 |
| clearance_microsomal | Clearance_Microsome_AZ | Spearman | 0.556 ± 0.019 | KERMT-routed; MAE only in the records | 0.626 ± 0.008 | 0.630 ± 0.010 | not listed | MapLight + GNN 0.630 ± 0.010 | 221 / 1102 |
| ames_mutagenicity | AMES | AUROC | 0.858 ± 0.005 | - | 0.868 ± 0.002 | 0.869 ± 0.002 | not listed | ZairaChem 0.871 ± 0.002 | 1453 / 7255 |
| dili_liver_injury | DILI | AUROC | 0.898 ± 0.022 | - | 0.887 ± 0.006 | 0.917 ± 0.005 | not listed | MiniMol 0.956 ± 0.006 | 96 / 475 |

Not compared:

- `herg_cardiotoxicity`: MARS trains on hERG_Karim with a self-generated scaffold split; TDC's hERG leaderboard uses the 655-compound hERG benchmark set.
- `ppb_binding`: MARS uses a human-only PPBR_AZ subset with a self-generated scaffold split; TDC's PPBR_AZ leaderboard uses its own split.

## Caveats that apply to every row

- **Audit status.** The blueprint (Module 11 section 4) says a 2026 audit found only CaliciBoost, MapLight and MapLight + GNN reproducible and leak-free. That audit was not located (one web search, 2026-10-24), so these entries are named as the blueprint names them and are not independently verified here. Every other entry, including each page's top entry, is unaudited.
- **Page notes.** The CYP2D6_Veith and CYP3A4_Veith pages print 'The lower the better' under an AUPRC metric while sorting highest first; the ordering used here is highest first. The Caco2_Wang page lists admet_ai_v2 at MAE 6.328, a value in a different unit, so it is not a usable entry.
- **Test sets.** MARS adopts TDC's benchmark split, then removes duplicates and re-standardizes, so its test set can differ from TDC's by a few molecules; the last column shows MARS's `n_test` and the size TDC prints for the whole dataset (not its test set).
- **Tuning.** MARS ran no hyperparameter search (`self_audit.md`). Leaderboard entries range from stock settings to heavy tuning, pretraining and external data.
- **DILI.** MARS trained on the DILIst-augmented pool (979 molecules, against TDC's 475). The number is not like-for-like.
- **Metric for clearance.** TDC scores `Clearance_Microsome_AZ` by Spearman; MARS reports MAE everywhere else. The Spearman here is computed from the same five XGBoost seed models. The KERMT clearance arm has MAE only in the records in git, so no KERMT value appears in that row.
- **Spread.** Both stds are seed-to-seed training noise on one fixed test set; neither includes test-set sampling noise (`evaluation_results.md` has bootstrap intervals for that).
- **Routing selection.** The served KERMT numbers belong to endpoints the routing rule chose because KERMT scored higher on these same test records.
- **Leaderboards move.** The pages show no date. Re-read them before quoting any value.
