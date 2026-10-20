# Explanation validation: XGBoost-served endpoints (TreeSHAP)

Measured 2026-10-20 by `ml/eval/explain_validation.py` on the **held-out test split** (`ml/data/processed/20260830T200000Z`),
against the promoted 5-seed XGBoost artifacts, using the same `explain_xgboost` the API serves. This is blueprint Module 6's
"dual validation" (ADR-029). It covers **XGBoost-served endpoints only**; the KERMT-served endpoints (Integrated Gradients) are
not validated yet because that engine is not built.

It tests whether the model's own output agrees with its explanation and whether the attribution lines up with published alert
definitions. It says nothing about the biology of a group. No number here is a claim that a highlighted group matters in the molecule.

## 1. Perturbation check

For each molecule: delete the atoms of the group with the largest absolute structure attribution (keeping the largest remaining
piece), re-run the model, and ask whether the output moved against the attribution's sign (a group that pushed the output up should
lower it when removed). The control deletes an equally sized, randomly placed connected set of atoms and asks the same question of
that set's own summed attribution. "Concordance" is the share of molecules where the answer is yes. 50% is chance.

| endpoint | molecules | top-group concordance | control concordance | mean abs shift (top) | mean abs shift (control) | sample |
|---|---|---|---|---|---|---|
| ames_mutagenicity | 287 | **0.78** | 0.63 | 1.92 | 1.63 | 400 random test molecules |
| dili_liver_injury | 92 | 0.49 | 0.50 | 0.62 | 0.67 | the whole test set (92 usable) |
| solubility_logs | 80 | 0.46 | 0.41 | 1.78 | 1.70 | 100 random test molecules |
| caco2_permeability | 67 | 0.64 | 0.60 | 0.36 | 0.44 | 100 random test molecules |

Reading it:
- **AMES: a real signal.** 0.78 against a 0.63 control, a difference of about 0.15 with a standard error near 0.04 (n = 287). The
  explanation's direction survives removing the group far more often than a random group's does.
- **DILI: none.** 0.49 against 0.50 on the whole (small) test set. The structure attribution for DILI predicts nothing about what
  removing a group does.
- **Solubility and Caco-2: no distinguishable lift** over the control (0.46 vs 0.41, 0.64 vs 0.60; samples of 67-80, standard
  error about 0.06). For regression endpoints the structure part is a small share of the explanation and deleting atoms also moves
  the whole-molecule descriptors, so this check cannot isolate it. Treat these two explanations as unvalidated.
- The mean absolute shift is the size of the output change, in the endpoint's output space (log-odds for classification). Removing
  the top group moves the output visibly more than the control on AMES (1.92 vs 1.63); on the other three the two are within 0.1 of each other.

## 2. Structural-alert cross-check (PAINS + Brenk)

For test molecules with at least one PAINS or Brenk alert match: the mean atom attribution inside the alert atoms, in the other
atoms of the same molecule, and in a size-matched random connected set. Units are log-odds per atom.

| endpoint | molecules with an alert | in alert atoms | in the rest | in random atoms | alert > rest | alert > random |
|---|---|---|---|---|---|---|
| ames_mutagenicity | 279 | +0.0725 | +0.0072 | +0.0264 | **0.75** | **0.64** |
| dili_liver_injury | 37 | +0.0005 | −0.0010 | +0.0003 | 0.54 | 0.51 |

- **AMES: alert atoms receive about ten times the attribution of the rest of the molecule, and more than random atoms in 64% of
  molecules.** This is the concrete "highlights known toxicophores" signal the blueprint asked for. A positive attribution here pushes
  the output toward the positive class (label 1) of this dataset.
- **DILI: indistinguishable from chance** (0.54 and 0.51). hERG is not in this table because it is KERMT-served.

## Caveats

- One random sample per endpoint (seed 0); samples are 67-287 molecules, so differences under about 0.1 are within noise.
- Deleting atoms changes the whole-molecule descriptors as well as the structure, and creates molecules outside the training
  distribution. The control shares both effects, which is why the lift over the control, not the raw concordance, is the number.
- The check uses the top group by absolute attribution, which can be a ring system or a very common group.
- Only XGBoost-served endpoints, and only four of the eight (AMES, DILI, solubility, Caco-2); HIA, PPB, CYP3A4 and CYP2C9 were not run. Nothing here applies to the
  KERMT-served endpoints.

## What this changes in the product

The inspector's note says attribution "has not been validated against known chemistry". That stays true for every endpoint except
that AMES now has the evidence above. A per-endpoint validation state in the UI is a design decision (not made here); until then
the note is deliberately general.

Reproduce:

```bash
cd ml && PYTHONPATH=.:../contracts python eval/explain_validation.py --prep-dir data/processed/20260830T200000Z \
    --endpoints ames_mutagenicity dili_liver_injury --n 400
```
