// Predict — single molecule. Composes the three columns: molecule input, the
// endpoint roster, and the inspector. It shows only what /predict returned: with no
// result yet (or no API configured) the roster is placeholders, never invented values
// (ADR-032). The roster, state derivation and reconciliation always come from
// ENDPOINT_METADATA, never the response (ADR-008).
import { useEffect, useMemo, useRef, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useCompareSession } from "../../app/compareSession";
import styles from "./predict.module.css";
import { useUiState } from "../../app/uiState";
import { usePredictSession } from "../../app/predictSession";
import { reconcile, requestedMlEndpoints } from "../../domain/reconcile";
import { ML_ENDPOINTS } from "../../domain/endpoints";
import { USING_API, ApiError, saveMolecule } from "../../data/client";
import { SaveControl } from "../../components/SaveControl";
import { buildMoleculeRequest, moleculeKey, saveNote } from "../../domain/save";
import { EndpointList } from "./EndpointList";
import { downloadText } from "../../data/download";
import { usePrintReport } from "../../components/report/usePrintReport";
import { useAnnounce } from "../../app/announce";
import { predictionAnnouncement } from "../../domain/announce";
import { buildCsv, predictFileName } from "../../domain/exportCsv";
import { EndpointSelector } from "./EndpointSelector";
import { EndpointDetail } from "./EndpointDetail";
import { StructureViewer } from "./StructureViewer";
import { PropertiesPanel } from "./PropertiesPanel";

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
  const { selectedEndpoint } = useUiState();
  const { smiles, setSmiles, selected, setSelected, result, running, error, canRun, run, clear } = usePredictSession();
  const usingApi = USING_API;
  const navigate = useNavigate();
  const compare = useCompareSession();

  const response = result?.response ?? null;
  const idle = !result && !running && !error;
  const placeholders = running || idle; // roster known, values not: quiet placeholder rows
  // Rows follow what the *last run* asked for, not the selector's current ticks, so
  // editing the selector never relabels results that were already produced.
  const requested = useMemo(
    () => (result ? requestedMlEndpoints(result.sent) : ML_ENDPOINTS),
    [result],
  );
  const recon = useMemo(
    () => reconcile(response, requested),
    [response, requested],
  );

  const selectedRow = recon.rows.find((r) => r.endpoint === selectedEndpoint) ?? recon.rows[0];

  function onSmilesKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      run();
    }
  }

  const failure = error ? requestFailure(error) : null;
  // Export is of a real result only, never a stale one after a failure.
  const exportCsv =
    usingApi && result && !failure
      ? () =>
          downloadText(
            predictFileName(result.response.molecule_id),
            buildCsv([{ smilesInput: result.submitted, response: result.response, cells: recon.rows }]),
          )
      : undefined;
  const printReport = usePrintReport();
  // A finished prediction is announced once (WCAG 4.1.3); a failure announces itself through its role="alert".
  const announce = useAnnounce();
  const announcedFor = useRef<unknown>(null);
  useEffect(() => {
    if (!usingApi || !result || failure || announcedFor.current === result) return;
    announcedFor.current = result;
    announce(predictionAnnouncement(recon.counts));
  }, [usingApi, result, failure, recon.counts, announce]);
  const openReport =
    usingApi && result && !failure
      ? () => printReport.print({ smilesInput: result.submitted, response: result.response, cells: recon.rows })
      : undefined;
  // What was actually submitted (the response's own input field is already standardized).
  const inputShown = result?.submitted;
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
              No API is configured (VITE_API_BASE is unset), so Run is disabled and no values are shown.
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
          {response?.properties && !failure && <PropertiesPanel properties={response.properties} />}
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
        <EndpointList recon={recon} loading={placeholders} idle={idle} onExport={exportCsv} onReport={openReport} />
      )}
      {printReport.element}

      {/* inspector */}
      <aside className={styles.inspector} aria-label="Endpoint detail">
        <div className={styles.insphd}>
          <span className={styles.panelTitle}>Endpoint detail</span>
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
                  ? "Saving needs the API."
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
