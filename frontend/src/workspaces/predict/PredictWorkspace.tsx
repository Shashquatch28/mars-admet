// Predict — single molecule. Composes the three columns: molecule input, the
// endpoint roster, and the inspector. When VITE_API_BASE is set it drives the
// real /predict response; otherwise it runs on the illustrative fixture (and the
// shell shows the "design prototype" strip). The roster, state derivation and
// reconciliation always come from ENDPOINT_METADATA, never the response (ADR-008).
import { useEffect, useMemo } from "react";
import styles from "./predict.module.css";
import { useUiState } from "../../app/uiState";
import { reconcile } from "../../domain/reconcile";
import { FIXTURE_RESPONSE, CELECOXIB_SMILES, emptyResponse } from "../../domain/fixtures";
import { usePrediction, USING_API } from "../../data/usePrediction";
import { ApiError } from "../../data/client";
import { EndpointList } from "./EndpointList";
import { EndpointDetail } from "./EndpointDetail";
import { StructureViewer } from "./StructureViewer";

export function PredictWorkspace() {
  const { selectedEndpoint, setIsSample } = useUiState();
  const smiles = CELECOXIB_SMILES;

  const query = usePrediction(smiles);
  const usingApi = USING_API;
  const loading = usingApi && query.isLoading;
  const isError = usingApi && query.isError;

  const response = usingApi ? (query.data ?? emptyResponse(smiles)) : FIXTURE_RESPONSE;
  const recon = useMemo(() => reconcile(response), [response]);

  // The prototype strip is shown while the values are the fixture (or no real
  // response has arrived yet).
  useEffect(() => {
    setIsSample(!usingApi || !query.data);
  }, [usingApi, query.data, setIsSample]);

  const selectedRow = recon.rows.find((r) => r.endpoint === selectedEndpoint) ?? recon.rows[0];

  return (
    <>
      {/* molecule column */}
      <section className={styles.molcol} aria-label="Molecule input">
        <div className={styles.panelhd}>
          <span className={styles.panelTitle}>Molecule input</span>
          <button className={styles.clr}>Clear</button>
        </div>
        <div className={styles.molbody}>
          <div>
            <div className={styles.flabel}>SMILES</div>
            <textarea className={styles.smiles} spellCheck={false} defaultValue={smiles} aria-label="SMILES" />
          </div>
          <div className={styles.runrow}>
            <button className={styles.btnPrimary}>Run prediction</button>
            <button className={styles.selbtn}>
              All 14 endpoints <span style={{ color: "var(--text-quiet)" }}>▾</span>
            </button>
            <kbd className={styles.kbd}>⌘⏎</kbd>
          </div>
          <div>
            <div className={styles.flabel}>Identity</div>
            <dl className={styles.idgrid}>
              <dt>Input</dt>
              <dd>{response.smiles_input.slice(0, 34)}…</dd>
              <dt>Standardized</dt>
              <dd>{(response.smiles_standardized || smiles).slice(0, 34)}…</dd>
            </dl>
            <span className={styles.rewrite}>Rewritten by standardizer</span>
            <dl className={styles.idgrid} style={{ marginTop: 8 }}>
              <dt>molecule_id</dt>
              <dd className={styles.idId}>{response.molecule_id || "—"}</dd>
            </dl>
          </div>
          <StructureViewer />
          <p className={styles.vnote}>
            Conformer is generated on demand and expires with the prediction cache. A 404 here is a normal
            state, not an error.
          </p>
        </div>
      </section>

      {/* results column */}
      {isError ? (
        <section className={styles.results} aria-label="Predictions">
          <div className={styles.reshd}>
            <span className={styles.resTitle}>Predictions</span>
          </div>
          <div style={{ padding: "24px 18px" }}>
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
                Request failed
              </div>
              <div style={{ fontFamily: "var(--mono)", color: "var(--text-tertiary)" }}>
                {query.error instanceof ApiError ? `${query.error.status} · ${query.error.message}` : String(query.error)}
              </div>
            </div>
          </div>
        </section>
      ) : (
        <EndpointList recon={recon} loading={loading} />
      )}

      {/* inspector */}
      <aside className={styles.inspector} aria-label="Endpoint detail">
        <div className={styles.insphd}>
          <span className={styles.panelTitle}>Endpoint detail</span>
          <button className={styles.inspx} aria-label="Close">
            ✕
          </button>
        </div>
        {selectedRow && !loading && !isError ? (
          <EndpointDetail row={selectedRow} response={response} />
        ) : (
          <div className={styles.inspbody}>
            <p className={styles.nostate}>
              {loading
                ? "Running…"
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
