// Compare: two or three molecules side by side. Descriptive, never evaluative (ADR-007).
//
//   - rows are the fixed roster in its fixed order; nothing is sorted by value or favourability
//   - there is no winner, rank, highlight or difference column; per_endpoint_winner is never read
//   - a value cell is mono, tabular, --text-primary in every state; reliability (out of domain,
//     stub, not returned) is a separate mark beside it and never recolours the value
//   - every molecule has a cell on every endpoint; one the service did not return says so
//   - /compare is anonymous, so unlike Batch and Library this screen is never gated
import { useEffect, useMemo, type KeyboardEvent } from "react";
import styles from "./compare.module.css";
import { useUiState } from "../../app/uiState";
import { useCompareSession } from "../../app/compareSession";
import { ApiError, USING_API } from "../../data/client";
import {
  COMPARE_MAX,
  COMPARE_MIN,
  buildComparison,
  compareFailure,
  repeatedSlots,
  type CompareColumn,
} from "../../domain/compare";
import { DISPLAY_UNIT, STUB_MODEL_ID } from "../../domain/endpoints";
import { fmtValue } from "../../domain/format";
import type { Row } from "../../domain/reconcile";
import { ReliabilityTag } from "../../components/dataviz/ReliabilityTag";

const clip = (s: string, n = 28) => (s.length > n ? `${s.slice(0, n)}…` : s);

function Cell({ row }: { row: Row }) {
  const { prediction, state, meta, reliability } = row;
  const edge =
    reliability === "ood" || reliability === "stub"
      ? styles.edgeAmber
      : reliability === "notreturned"
        ? styles.edgeMuted
        : reliability === "notrequested"
          ? styles.edgeDashed
          : "";
  let value;
  if (state.kind === "not_returned") value = <span className={styles.na}>not returned</span>;
  else if (state.kind === "not_requested") value = <span className={styles.na}>not requested</span>;
  else if (prediction) {
    const text = fmtValue(prediction, meta);
    value = (
      <span className={styles.val}>
        {state.kind === "stub_served" || prediction.model_id === STUB_MODEL_ID ? <span className={styles.hatch}>{text}</span> : text}
      </span>
    );
  } else value = <span className={styles.val} />;
  return (
    <td className={`${styles.cell} ${edge}`}>
      {value}
      <ReliabilityTag reliability={reliability} />
    </td>
  );
}

function FlagLine({ c }: { c: CompareColumn }) {
  return (
    <span className={styles.flags}>
      <b>{c.flags.outOfDomain}</b> out of domain · <b>{c.flags.stubServed}</b> stub-served · <b>{c.flags.notReturned}</b> not
      returned
    </span>
  );
}

export function CompareWorkspace() {
  const { setIsSample } = useUiState();
  useEffect(() => setIsSample(false), [setIsSample]); // no fixture here: nothing on screen is illustrative

  const s = useCompareSession();
  const comparison = useMemo(() => (s.result ? buildComparison(s.result) : null), [s.result]);
  const repeats = repeatedSlots(s.slots);
  const failure = s.error
    ? compareFailure(s.error instanceof ApiError ? s.error.status : 0, s.error.message)
    : null;

  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      s.run();
    }
  };

  return (
    <section className={styles.cmp} aria-label="Compare">
      <div className={styles.hd}>
        <span className={styles.title}>Compare</span>
        <span className={styles.sub}>
          {COMPARE_MIN} to {COMPARE_MAX} molecules, side by side
        </span>
      </div>

      <div className={styles.inputs}>
        {s.slots.map((value, i) => (
          <label key={i} className={styles.slot}>
            <span className={styles.slotLabel}>Molecule {i + 1}</span>
            <input
              value={value}
              disabled={s.running}
              onChange={(e) => s.setSlot(i, e.target.value)}
              onKeyDown={onKey}
              spellCheck={false}
              placeholder="SMILES"
              aria-label={`Molecule ${i + 1} SMILES`}
            />
          </label>
        ))}
        <div className={styles.actions}>
          {s.slots.length < COMPARE_MAX ? (
            <button type="button" onClick={s.addThird} disabled={s.running}>
              Add a third molecule
            </button>
          ) : (
            <button type="button" onClick={s.removeThird} disabled={s.running}>
              Remove the third
            </button>
          )}
          <button type="button" className={styles.go} onClick={s.run} disabled={!s.canRun}>
            {s.running ? "Running…" : "Run comparison"}
          </button>
          <button type="button" onClick={s.clear} disabled={s.running}>
            Clear
          </button>
        </div>
      </div>

      <div className={styles.status} role={failure ? "alert" : "status"}>
        {failure ? (
          <>
            <b className={styles.failTitle}>{failure.title}</b> <span className={styles.failDetail}>{failure.detail}</span>
          </>
        ) : s.running ? (
          "The service predicts each molecule in turn. A molecule it has not seen before takes longer than one it has cached."
        ) : s.problem && !s.result ? (
          s.problem
        ) : repeats.length > 0 ? (
          `Molecule ${repeats.map((i) => i + 1).join(" and ")} repeats an earlier entry.`
        ) : comparison ? (
          `${comparison.columns.length} molecules compared.${comparison.modelVersions.length > 1 ? ` Served by different model versions: ${comparison.modelVersions.join(", ")}.` : ""}`
        ) : (
          ""
        )}
      </div>

      <div className={styles.body}>
        {!USING_API ? (
          <p className={styles.empty}>No API is configured, so Compare has nothing to run. It takes SMILES strings and asks the service.</p>
        ) : !comparison ? (
          <p className={styles.empty}>
            Enter two or three SMILES strings and run the comparison. Values appear side by side with the same
            reliability marks as Predict. Nothing is ranked, scored or called better: MARS defines no direction of
            good, so a higher or lower value is not a better or worse molecule.
          </p>
        ) : (
          <table className={styles.table}>
            <caption className={styles.sr}>
              Predicted values for {comparison.columns.length} molecules across the endpoint roster, in roster order
            </caption>
            <thead>
              <tr>
                <th scope="col" className={styles.corner}>
                  Endpoint
                </th>
                {comparison.columns.map((c) => (
                  <th key={c.index} scope="col" className={styles.molhd}>
                    <span className={styles.molName}>Molecule {c.index + 1}</span>
                    <span className={styles.molSmiles} title={c.smilesStandardized || c.smilesInput}>
                      {clip(c.smilesStandardized || c.smilesInput)}
                    </span>
                    <FlagLine c={c} />
                  </th>
                ))}
                <th scope="col" className={styles.unithd}>
                  Unit
                </th>
              </tr>
            </thead>
            {comparison.groups.map((g) => (
              <tbody key={g.group}>
                <tr>
                  <th colSpan={comparison.columns.length + 2} scope="colgroup" className={styles.grp}>
                    {g.label}
                  </th>
                </tr>
                {g.rows.map((r) => (
                  <tr key={r.endpoint}>
                    <th scope="row" className={styles.ep}>
                      {r.endpoint}
                    </th>
                    {r.cells.map((cell, i) => (
                      <Cell key={i} row={cell} />
                    ))}
                    <td className={styles.unit}>{DISPLAY_UNIT[r.endpoint]}</td>
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        )}
      </div>
    </section>
  );
}
