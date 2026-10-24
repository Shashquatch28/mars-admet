// Molecule: what the structure of the molecule last run in Predict is, apart from what the models say about it.
// The 2D drawing, the computed properties and the structural alerts live here so the Predict column stays a place
// to enter a molecule and read its predictions. Nothing on this page is a prediction: it reads the response
// Predict already holds (usePredictSession), asks the model for nothing, and has no endpoint, value or roster.
// With no result there is no molecule, and the page says so rather than drawing a stand-in.
import { Link } from "react-router-dom";
import { usePredictSession } from "../../app/predictSession";
import { StructureDepiction } from "../../components/StructureDepiction";
import { PropertiesPanel } from "../predict/PropertiesPanel";
import predict from "../predict/predict.module.css";
import styles from "./molecule.module.css";

// Truncate for the identity grid; only mark it as truncated when it was.
const clip = (s: string, n = 44) => (s.length > n ? `${s.slice(0, n)}…` : s);

export function MoleculeWorkspace() {
  const { result, running, error } = usePredictSession();
  const response = result?.response ?? null;

  return (
    <section className={styles.page} aria-label="Molecule">
      <div className={styles.hd}>
        <span className={styles.title}>Molecule</span>
        <span className={styles.sub}>
          {response ? "Computed from the structure of the molecule last run in Predict" : "No molecule yet"}
        </span>
      </div>
      {!response ? (
        <div className={styles.empty}>
          <p>
            {running
              ? "Running…"
              : error
                ? "The last run did not return a molecule, so there is no structure to show."
                : "The structure drawing and the computed properties of a molecule appear here once Predict has run it."}
          </p>
          <Link to="/predict" className={styles.link}>
            Go to Predict
          </Link>
        </div>
      ) : (
        <div className={styles.body}>
          <div className={styles.col}>
            <div>
              <div className={predict.flabel}>Identity</div>
              <dl className={predict.idgrid}>
                <dt>Input</dt>
                <dd>{result?.submitted ? clip(result.submitted) : "—"}</dd>
                <dt>Standardized</dt>
                <dd>{clip(response.smiles_standardized)}</dd>
                <dt>molecule_id</dt>
                <dd className={predict.idId}>{response.molecule_id || "—"}</dd>
              </dl>
            </div>
            <StructureDepiction smiles={response.smiles_standardized} />
            <Link to="/predict" className={styles.link}>
              Back to the predictions
            </Link>
          </div>
          <div className={styles.col}>
            {response.properties ? (
              <PropertiesPanel properties={response.properties} />
            ) : (
              <p className={predict.vnote}>This service version did not return computed properties for this molecule.</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
