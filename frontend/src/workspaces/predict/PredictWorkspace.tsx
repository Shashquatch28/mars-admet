// Predict — single molecule. Composes the three columns: molecule input, the
// endpoint roster, and the inspector. When VITE_API_BASE is set it drives the
// real /predict response; otherwise it runs on the illustrative fixture (and the
// shell shows the "design prototype" strip). The roster, state derivation and
// reconciliation always come from ENDPOINT_METADATA, never the response (ADR-008).
import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useCompareSession } from "../../app/compareSession";
import styles from "./predict.module.css";
import { useUiState } from "../../app/uiState";
import { usePredictSession } from "../../app/predictSession";
import { reconcile, requestedMlEndpoints } from "../../domain/reconcile";
import { ML_ENDPOINTS } from "../../domain/endpoints";
import { FIXTURE_RESPONSE, emptyResponse } from "../../domain/fixtures";
import { USING_API, ApiError, saveMolecule } from "../../data/client";
import { SaveControl } from "../../components/SaveControl";
import { buildMoleculeRequest, moleculeKey, saveNote } from "../../domain/save";
import { EndpointList } from "./EndpointList";
import { downloadText } from "../../data/download";
import { buildCsv, predictFileName } from "../../domain/exportCsv";
import { EndpointSelector } from "./EndpointSelector";
import { EndpointDetail } from "./EndpointDetail";
import { StructureViewer } from "./StructureViewer";
import { atomHighlights, explainView, focusHighlights, fragmentKey } from "../../domain/explain";
import { useExplanation } from "../../data/useExplanation";

// Truncate for the identity grid; only mark it as truncated when it was.
const clip = (s: string, n = 34) => (s.length > n ? `${s.slice(0, n)}…` : s);

function requestFailure(error: Error): { title: string; detail: string } {
  if (error instanceof ApiError) {
    const title =
      error.status === 422 ? "Molecule rejected" : error.status === 429 ? "Rate limited" : "Request failed";
    return { title, detail: error.status > 0 ? `${error.status} · ${error.message}` : error.message };
  }
  return { title: "Request failed", detail: String(error) };
}

export function PredictWorkspace() {
  const { selectedEndpoint, setIsSample } = useUiState();
  const { smiles, setSmiles, selected, setSelected, result, running, error, canRun, run, clear } = usePredictSession();
  const usingApi = USING_API;
  const navigate = useNavigate();
  const compare = useCompareSession();

  // The prototype strip is shown only while the values on screen are the fixture.
  // A live session with no result has no values at all, so nothing there is illustrative.
  useEffect(() => {
    setIsSample(!usingApi);
  }, [usingApi, setIsSample]);

  const response = usingApi ? (result?.response ?? null) : FIXTURE_RESPONSE;
  const idle = usingApi && !result && !running && !error;
  const placeholders = running || idle; // roster known, values not: quiet placeholder rows
  // Rows follow what the *last run* asked for, not the selector's current ticks, so
  // editing the selector never relabels results that were already produced.
  const requested = useMemo(
    () => (usingApi && result ? requestedMlEndpoints(result.sent) : ML_ENDPOINTS),
    [usingApi, result],
  );
  const recon = useMemo(
    () => reconcile(response ?? emptyResponse(smiles), requested),
    [response, smiles, requested],
  );

  const selectedRow = recon.rows.find((r) => r.endpoint === selectedEndpoint) ?? recon.rows[0];

  // Explanation (ADR-029). Asked for per molecule + endpoint, never automatically; the answer is
  // shared by the inspector and the structure viewer, which read the same query.
  const [asked, setAsked] = useState<ReadonlySet<string>>(new Set());
  const [showOnStructure, setShowOnStructure] = useState(true);
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const moleculeId = usingApi && result ? result.response.molecule_id : null;
  const explainKey = moleculeId && selectedRow ? `${moleculeId}:${selectedRow.endpoint}` : "";
  const explainAsked = asked.has(explainKey);
  const exp = useExplanation(moleculeId, selectedRow?.endpoint ?? "solubility_logs", explainAsked);
  const explanation = explainView({
    rowState: selectedRow?.state ?? { kind: "not_returned" },
    prediction: selectedRow?.prediction,
    asked: explainAsked,
    isPending: exp.isFetching,
    data: exp.data,
    error: exp.error as { status?: number; message: string } | null,
  });
  const highlights = useMemo(() => {
    if (explanation.kind !== "ready" || !showOnStructure) return null;
    const all = atomHighlights(explanation.data.atom_attributions);
    const focused = focusKey ? explanation.data.fragment_attributions.find((f) => fragmentKey(f) === focusKey) : undefined;
    return focused ? focusHighlights(all, focused.atom_indices) : all;
  }, [explanation, showOnStructure, focusKey]);

  function onSmilesKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      run();
    }
  }

  const failure = error ? requestFailure(error) : null;
  // Export is of a real result only: never the illustrative sample, never a stale one after a failure.
  const exportCsv =
    usingApi && result && !failure
      ? () =>
          downloadText(
            predictFileName(result.response.molecule_id),
            buildCsv([{ smilesInput: result.submitted, response: result.response, cells: recon.rows }]),
          )
      : undefined;
  // Fixture: the response's own input field. Live: what was actually submitted.
  const inputShown = usingApi ? result?.submitted : response?.smiles_input;
  const rewritten = !!response && !!inputShown && inputShown !== response.smiles_standardized;

  return (
    <>
      {/* molecule column */}
      <section className={styles.molcol} aria-label="Molecule input">
        <div className={styles.panelhd}>
          <span className={styles.panelTitle}>Molecule input</span>
          <button className={styles.clr} onClick={clear} disabled={!smiles && !result && !error}>
            Clear
          </button>
        </div>
        <div className={styles.molbody}>
          <div>
            <div className={styles.flabel}>SMILES</div>
            <textarea
              className={styles.smiles}
              spellCheck={false}
              value={smiles}
              onChange={(e) => setSmiles(e.target.value)}
              onKeyDown={onSmilesKey}
              placeholder={usingApi ? "Paste or type a SMILES string" : undefined}
              aria-label="SMILES"
            />
          </div>
          <div className={styles.runrow}>
            <button className={styles.btnPrimary} onClick={run} disabled={!canRun}>
              {running ? "Running…" : "Run prediction"}
            </button>
            <EndpointSelector selected={selected} onChange={setSelected} disabled={!usingApi || running} />
            <kbd className={styles.kbd}>⌘⏎</kbd>
          </div>
          {!usingApi && (
            <p className={styles.vnote}>
              No API configured (VITE_API_BASE is unset), so Run is disabled and the roster shows the
              illustrative fixture.
            </p>
          )}
          <div>
            <div className={styles.flabel}>Identity</div>
            <dl className={styles.idgrid}>
              <dt>Input</dt>
              <dd>{inputShown ? clip(inputShown) : "—"}</dd>
              <dt>Standardized</dt>
              <dd>{response ? clip(response.smiles_standardized) : "—"}</dd>
            </dl>
            {rewritten && <span className={styles.rewrite}>Rewritten by standardizer</span>}
            <dl className={styles.idgrid} style={{ marginTop: 8 }}>
              <dt>molecule_id</dt>
              <dd className={styles.idId}>{response?.molecule_id || "—"}</dd>
            </dl>
          </div>
          <StructureViewer live={usingApi} moleculeId={response?.molecule_id} highlights={highlights} />
          <p className={styles.vnote}>
            Conformer is generated on demand and expires with the prediction cache. A 404 here is a normal
            state, not an error.
          </p>
        </div>
      </section>

      {/* results column */}
      {failure ? (
        <section className={styles.results} aria-label="Predictions">
          <div className={styles.reshd}>
            <span className={styles.resTitle}>Predictions</span>
          </div>
          <div style={{ padding: "24px 18px" }} role="alert">
            <div
              style={{
                border: "1px solid var(--error)",
                borderRadius: "var(--radius-sm)",
                padding: 14,
                color: "var(--text-secondary)",
                fontSize: 11,
                lineHeight: 1.6,
                maxWidth: "56ch",
              }}
            >
              <div
                style={{
                  fontFamily: "var(--cond)",
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  fontSize: 9,
                  color: "var(--error)",
                  marginBottom: 8,
                }}
              >
                {failure.title}
              </div>
              <div style={{ fontFamily: "var(--mono)", color: "var(--text-tertiary)" }}>{failure.detail}</div>
            </div>
          </div>
        </section>
      ) : (
        <EndpointList recon={recon} loading={placeholders} idle={idle} onExport={exportCsv} />
      )}

      {/* inspector */}
      <aside className={styles.inspector} aria-label="Endpoint detail">
        <div className={styles.insphd}>
          <span className={styles.panelTitle}>Endpoint detail</span>
          <button className={styles.inspx} aria-label="Close">
            ✕
          </button>
        </div>
        {selectedRow && response && !failure ? (
          <EndpointDetail
            row={selectedRow}
            response={response}
            explanation={{
              view: explanation,
              canAsk: usingApi && !!moleculeId && !!explainKey,
              onAsk: () => {
                if (!explainKey) return;
                if (explainAsked) void exp.refetch(); // "Try again" after a failure
                else setAsked((prev) => new Set(prev).add(explainKey));
              },
              showOnStructure,
              onShowOnStructure: setShowOnStructure,
              focusKey,
              onFocus: setFocusKey,
            }}
          />
        ) : (
          <div className={styles.inspbody}>
            <p className={styles.nostate}>
              {running
                ? "Running…"
                : failure
                  ? "No prediction to inspect."
                  : idle
                    ? "No prediction yet. Enter a SMILES string and run it to inspect an endpoint."
                    : "Select an endpoint to inspect its seed spread, applicability-domain distance and the model artifact that served it."}
            </p>
          </div>
        )}
        <div className={styles.inspfoot} style={{ flexWrap: "wrap" }}>
          <button
            className={styles.ibtn}
            disabled={!(usingApi && result && !failure)}
            onClick={() => {
              if (!result) return;
              compare.seedFirst(result.submitted); // what the user typed, not a rewritten form
              navigate("/compare");
            }}
          >
            Compare molecule
          </button>
          <SaveControl
            kind="molecule"
            withLabel
            buttonClassName={styles.ibtn}
            buttonLabel="Save to library"
            markKey={usingApi && result && !failure ? moleculeKey(result.response) : null}
            disabledReason={
              usingApi && result && !failure
                ? null
                : !usingApi
                  ? "Saving needs the API. These values are sample data."
                  : running
                    ? "Wait for the run to finish."
                    : "Run a molecule to save it."
            }
            note={saveNote("molecule", result?.response.model_version ?? null)}
            save={(input) => saveMolecule(buildMoleculeRequest(result!.response, input))}
          />
        </div>
      </aside>
    </>
  );
}
