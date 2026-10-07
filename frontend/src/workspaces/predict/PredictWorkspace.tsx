// Predict — single molecule. Composes the three columns: molecule input, the
// endpoint roster, and the inspector. When VITE_API_BASE is set it drives the
// real /predict response; otherwise it runs on the illustrative fixture (and the
// shell shows the "design prototype" strip). The roster, state derivation and
// reconciliation always come from ENDPOINT_METADATA, never the response (ADR-008).
import { useEffect, useMemo, type KeyboardEvent } from "react";
import styles from "./predict.module.css";
import { useUiState } from "../../app/uiState";
import { usePredictSession } from "../../app/predictSession";
import { reconcile } from "../../domain/reconcile";
import { FIXTURE_RESPONSE, emptyResponse } from "../../domain/fixtures";
import { USING_API, ApiError } from "../../data/client";
import { EndpointList } from "./EndpointList";
import { EndpointDetail } from "./EndpointDetail";
import { StructureViewer } from "./StructureViewer";

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
  const { smiles, setSmiles, result, running, error, canRun, run, clear } = usePredictSession();
  const usingApi = USING_API;

  // The prototype strip is shown only while the values on screen are the fixture.
  // A live session with no result has no values at all, so nothing there is illustrative.
  useEffect(() => {
    setIsSample(!usingApi);
  }, [usingApi, setIsSample]);

  const response = usingApi ? (result?.response ?? null) : FIXTURE_RESPONSE;
  const idle = usingApi && !result && !running && !error;
  const placeholders = running || idle; // roster known, values not: quiet placeholder rows
  const recon = useMemo(() => reconcile(response ?? emptyResponse(smiles)), [response, smiles]);

  const selectedRow = recon.rows.find((r) => r.endpoint === selectedEndpoint) ?? recon.rows[0];

  function onSmilesKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      run();
    }
  }

  const failure = error ? requestFailure(error) : null;
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
            <button className={styles.selbtn}>
              All 14 endpoints <span style={{ color: "var(--text-quiet)" }}>▾</span>
            </button>
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
          <StructureViewer live={usingApi} moleculeId={response?.molecule_id} />
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
        <EndpointList recon={recon} loading={placeholders} idle={idle} />
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
          <EndpointDetail row={selectedRow} response={response} />
        ) : (
          <div className={styles.inspbody}>
            <p className={styles.nostate}>
              {running
                ? "Running…"
                : failure
                  ? "No prediction to inspect."
                  : idle
                    ? "No prediction yet. Enter a SMILES string and run it to inspect an endpoint."
                    : "Select an endpoint to inspect its interval, applicability-domain distance and the model artifact that served it."}
            </p>
          </div>
        )}
        <div className={styles.inspfoot}>
          <button className={styles.ibtn}>Compare molecule</button>
          <button className={styles.ibtn}>Save to library</button>
        </div>
      </aside>
    </>
  );
}
