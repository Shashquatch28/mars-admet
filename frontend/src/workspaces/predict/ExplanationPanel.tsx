// Explanation section of the inspector (ADR-031). The model that served the value explains it.
// Attribution is signed, never good or bad: the sign is a glyph and a signed number first, a hue
// second. Every state is said in words in the panel itself, none only in a tooltip (never-do #8).
// The panel computes nothing: `explainView` decides what to show and this renders it.
import styles from "./predict.module.css";
import type { Endpoint } from "../../types/contracts";
import {
  GLYPH,
  convergenceNote,
  describeJob,
  fmtSigned,
  fragmentKey,
  methodLabel,
  outputSpaceLabel,
  seedAgreementNote,
  topFragments,
  totalRows,
  type ExplainView,
  type Sign,
} from "../../domain/explain";
import { fmtNum } from "../../domain/format";

const SIGN_WORD: Record<Sign, string> = { up: "pushed the output up", down: "pushed the output down", none: "no direction" };

function Mark({ sign }: { sign: Sign }) {
  const cls = sign === "up" ? styles.sUp : sign === "down" ? styles.sDown : styles.sNone;
  return (
    <span className={`${styles.smark} ${cls}`} role="img" aria-label={SIGN_WORD[sign]}>
      {GLYPH[sign]}
    </span>
  );
}

export interface ExplanationPanelProps {
  endpoint: Endpoint;
  view: ExplainView;
  canAsk: boolean; // false when there is no API to ask
  onAsk: () => void; // start, or start again
  onCancel: () => void; // stop a queued or running job
  showOnStructure: boolean;
  onShowOnStructure: (on: boolean) => void;
  focusKey: string | null; // a group chosen from the list: only its atoms are drawn on the structure
  onFocus: (key: string | null) => void;
}

export function ExplanationPanel({
  endpoint,
  view,
  canAsk,
  onAsk,
  onCancel,
  showOnStructure,
  onShowOnStructure,
  focusKey,
  onFocus,
}: ExplanationPanelProps) {
  const ask = (label: string) => (
    <button className={styles.xbtn} onClick={onAsk} disabled={!canAsk}>
      {label}
    </button>
  );
  let body: React.ReactNode;

  switch (view.kind) {
    case "not_askable":
      body = <p className={styles.nostate}>{view.why}</p>;
      break;
    case "checking":
      body = <p className={styles.nostate}>Checking whether this has already been explained.</p>;
      break;
    case "idle":
      body = (
        <>
          <p className={styles.nostate}>
            Computed on request, from the model that served this value. It describes what moved that model&rsquo;s
            output, not why the molecule behaves as it does.
          </p>
          {view.background && (
            <p className={styles.nostate}>
              This is a graph model, so its explanation runs in the background and can take several minutes. It keeps
              running if you leave this page, and the result is kept for 48 hours.
            </p>
          )}
          {view.cancelled && <p className={styles.nostate}>Cancelled. Nothing was kept.</p>}
          {ask("Explain this prediction")}
          {!canAsk && <p className={styles.nostate}>Explanations need the API.</p>}
        </>
      );
      break;
    case "starting":
      body = <p className={styles.nostate}>Starting the explanation.</p>;
      break;
    case "job": {
      const d = describeJob(view.job);
      body = (
        <>
          <p className={styles.nostate}>{d.status}</p>
          {d.detail && <p className={styles.nostate}>{d.detail}</p>}
          <p className={styles.nostate}>{d.elapsed}</p>
          <p className={styles.xnote}>
            The number of integration steps grows (64, then 128, then 256) until the result is accurate enough, so
            there is no percentage and no time left to show. This page checks every few seconds. It is safe to leave:
            the job keeps running, and opening this endpoint again picks it up.
          </p>
          <button className={styles.xbtn} onClick={onCancel} disabled={view.stopping}>
            {view.stopping ? "Stopping" : "Cancel"}
          </button>
          {view.stopping && (
            <p className={styles.xnote}>A running job stops between steps, which takes a few seconds.</p>
          )}
        </>
      );
      break;
    }
    case "mismatch":
      body = (
        <p className={styles.nostate}>
          This value came from {view.served}, but the explanation is of {view.explained}. They are not shown together,
          because the explanation would describe a model that did not produce the number above. Run the molecule again
          to explain the model that serves it now.
        </p>
      );
      break;
    case "no_model":
      body = <p className={styles.nostate}>{view.message}</p>;
      break;
    case "expired":
      body = (
        <p className={styles.nostate}>
          This molecule&rsquo;s cache entry has expired, so it can no longer be explained. Run it again to regenerate.
        </p>
      );
      break;
    case "unsupported":
      body = <p className={styles.nostate}>This API environment has no model stack, so it cannot explain predictions.</p>;
      break;
    case "unexplainable":
      body = (
        <p className={styles.nostate}>
          This molecule cannot be explained: {view.message} Starting it again would give the same answer.
        </p>
      );
      break;
    case "limited":
      body = (
        <>
          <p className={styles.nostate}>{view.message}</p>
          {ask("Try again")}
        </>
      );
      break;
    case "busy":
      body = (
        <>
          <p className={styles.nostate}>
            {view.message} The explanation is not replaced by a different model&rsquo;s.
          </p>
          {ask("Try again")}
        </>
      );
      break;
    case "error":
      body = (
        <>
          <p className={styles.nostate}>Explanation request failed: {view.message}</p>
          {ask("Try again")}
        </>
      );
      break;
    case "ready": {
      const d = view.data;
      const dp = endpoint === "ppb_binding" && d.output_space === "native_unit" ? 1 : 2;
      const space = outputSpaceLabel(d.output_space, endpoint);
      body = (
        <>
          <dl className={styles.ikv}>
            <dt>Method</dt>
            <dd>{methodLabel(d.method)}</dd>
            <dt>Model</dt>
            <dd className={styles.ddProv}>{d.model_id}</dd>
            <dt>Seeds averaged</dt>
            <dd>{d.n_seeds}</dd>
            <dt>Units</dt>
            <dd>{space}</dd>
            {d.n_steps != null && (
              <>
                <dt>Integration steps</dt>
                <dd>{d.n_steps}</dd>
              </>
            )}
            <dt>Completeness error</dt>
            <dd>{fmtNum(d.completeness_error, 4)}</dd>
            {d.converged != null && (
              <>
                <dt>Met tolerance</dt>
                <dd>{d.converged ? "yes" : "no"}</dd>
              </>
            )}
            {d.seed_agreement != null && (
              <>
                <dt>Seed agreement</dt>
                <dd>{fmtNum(d.seed_agreement, 2)}</dd>
              </>
            )}
          </dl>
          {convergenceNote(d) && <p className={styles.xnote}>{convergenceNote(d)}</p>}
          {seedAgreementNote(d) && <p className={styles.xnote}>{seedAgreementNote(d)}</p>}

          <div className={styles.xsub}>Parts that add up to the output</div>
          <table className={styles.xtable}>
            <tbody>
              {totalRows(d, dp).map((r) => (
                <tr key={r.key}>
                  <th scope="row">{r.label}</th>
                  <td>
                    <Mark sign={r.sign} />
                  </td>
                  <td className={styles.xnum}>{r.text}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className={styles.xnote}>
            ▲ pushed the output up from the reference, ▼ pushed it down. The sign gives direction only; it is not a
            judgement.
          </p>
          <p className={styles.xnote}>Reference: {d.baseline}</p>

          <div className={styles.xsub}>Structure: largest groups</div>
          {d.fragment_attributions.length === 0 ? (
            <p className={styles.nostate}>No named group matched this molecule. The per-atom values are still used on the structure.</p>
          ) : (
            <ul className={styles.xlist}>
              {topFragments(d).map((f) => (
                <li key={fragmentKey(f)} className={styles.xli}>
                  <button
                    className={styles.xrow}
                    aria-pressed={focusKey === fragmentKey(f)}
                    onClick={() => onFocus(focusKey === fragmentKey(f) ? null : fragmentKey(f))}
                  >
                    <Mark sign={f.score === 0 ? "none" : f.score > 0 ? "up" : "down"} />
                    <span className={styles.xname}>{f.name}</span>
                    <span className={styles.xnum}>{fmtSigned(f.score, dp)}</span>
                    <span className={styles.xcount}>{f.atom_indices.length} {f.atom_indices.length === 1 ? "atom" : "atoms"}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className={styles.xnote}>
            Groups overlap, so their scores do not add up. The atoms do.{" "}
            {focusKey ? "Showing only the chosen group on the structure; choose it again to show every atom." : "Choose a group to show only its atoms on the structure."}
          </p>

          <div className={styles.xsub}>Whole molecule: largest descriptors</div>
          <ul className={styles.xlist}>
            {d.whole_molecule_attributions.slice(0, 6).map((x) => (
              <li key={x.name}>
                <Mark sign={x.score === 0 ? "none" : x.score > 0 ? "up" : "down"} />
                <span className={styles.xname}>{x.name}</span>
                <span className={styles.xnum}>{fmtSigned(x.score, dp)}</span>
                <span className={styles.xcount}>{x.value == null ? "n/a" : fmtNum(x.value, 2)}</span>
              </li>
            ))}
          </ul>
          <p className={styles.xnote}>
            These are properties of the whole molecule, so they cannot be drawn on atoms. The structure part above is
            only the share of the explanation that can be.
          </p>

          <button
            className={styles.xbtn}
            aria-pressed={showOnStructure}
            onClick={() => onShowOnStructure(!showOnStructure)}
          >
            {showOnStructure ? "Hide on structure" : "Show on structure"}
          </button>
          <p className={styles.xnote}>
            Attribution describes the model&rsquo;s output. It has not been validated against known chemistry, so a
            highlighted group is not evidence that it matters in the molecule.
          </p>
        </>
      );
      break;
    }
  }

  return (
    <div className={styles.isec}>
      <div className={styles.seclbl}>Explanation</div>
      <div className={styles.xbody}>{body}</div>
    </div>
  );
}
