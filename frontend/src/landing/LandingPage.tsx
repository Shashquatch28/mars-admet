// The front door (ADR-046): what MARS is, a molecule input that hands off to Predict, a live example of
// the roster, what a MARS number is not, and the five workspaces. It lives outside the app shell (no rail,
// no status bar) but inside the same providers, so its input is the Predict session's input: the molecule
// typed here is the molecule Predict opens with, already running. Instant in, instant out: no animation.
import { useEffect, useState, type KeyboardEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import styles from "./landing.module.css";
import { MoleculeArt } from "./MoleculeArt";
import { Specimen } from "./Specimen";
import { EXAMPLE_SMILES, markLandingSeen } from "./entry";
import { usePredictSession } from "../app/predictSession";
import { useAuthSession } from "../app/authSession";
import { USING_API } from "../data/client";
import { useApiHealth } from "../data/useApiHealth";
import { useGenerations } from "../data/useGenerations";
import { ADMET } from "./admet";
import { ML_ENDPOINTS } from "../domain/endpoints";
import { isGatedPath } from "../domain/session";

const WORKSPACES = [
  { key: "1", path: "/predict", name: "Predict", text: "One molecule, every endpoint, with a 3D view and an explanation." },
  { key: "2", path: "/batch", name: "Batch", text: "Upload a CSV or SDF and see what each endpoint returned across the set." },
  { key: "3", path: "/compare", name: "Compare", text: "Two or three molecules side by side. Descriptive only, no winner." },
  { key: "4", path: "/library", name: "Library", text: "Saved snapshots, frozen as they were when you saved them." },
  { key: "5", path: "/molecule", name: "Molecule", text: "Structure, name and computed properties for one molecule." },
] as const;

const SCOPE = [
  {
    title: "No verdict.",
    text: "A value is never coloured, ranked or called safe, risky or favourable. Compare lines molecules up side by side and names no winner.",
  },
  {
    title: "Spread is not confidence.",
    text: "The ± is the spread across 5 cross-validation seeds. A narrow spread is not reassurance and a wide one is not a warning.",
  },
  {
    title: "Domain describes the data.",
    text: "The applicability-domain gauge measures how well an endpoint's training set covers the molecule. It says nothing about the molecule itself.",
  },
  {
    title: "Gaps stay visible.",
    text: "An endpoint the service did not return appears as NOT RETURNED. It is never hidden and never filled in.",
  },
] as const;

function InputBar({
  id,
  large,
  smiles,
  onChange,
  onPredict,
}: {
  id: string;
  large?: boolean;
  smiles: string;
  onChange: (s: string) => void;
  onPredict: () => void;
}) {
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      onPredict();
    }
  };
  return (
    <div className={styles.bar}>
      <input
        id={id}
        className={styles.barInput}
        type="text"
        value={smiles}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKey}
        placeholder="Paste a SMILES string"
        aria-label={large ? undefined : "SMILES"}
        aria-labelledby={large ? `${id}-label` : undefined}
        spellCheck={false}
        autoComplete="off"
      />
      <button className={styles.barGo} type="button" onClick={onPredict}>
        Predict
      </button>
    </div>
  );
}

export function LandingPage() {
  const navigate = useNavigate();
  const { runWith } = usePredictSession();
  const { status } = useAuthSession();
  const health = useApiHealth();
  const generations = useGenerations();
  const [smiles, setSmiles] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    document.title = "MARS · ADMET Rapid Screening";
  }, []);

  const apiNote = !USING_API
    ? "No API is configured, so Predict cannot run."
    : health === "unreachable"
      ? "The API is unreachable, so Predict cannot run right now."
      : "";

  // Every way into the app remembers that the landing has been seen, so "/" goes straight to Predict next time.
  function enter(to: string) {
    markLandingSeen();
    navigate(to);
  }
  function predict() {
    if (!smiles.trim()) {
      setNote("Enter a SMILES string, or use the example.");
      return;
    }
    if (apiNote) {
      setNote(apiNote);
      return;
    }
    runWith(smiles);
    enter("/predict");
  }

  const categories = ADMET.length;

  return (
    <div className={styles.page}>
      <a className={styles.skip} href="#landing-main">
        Skip to content
      </a>

      <header className={styles.topbar}>
        <Link className={styles.brand} to="/welcome" aria-label="MARS ADMET Rapid Screening, overview">
          <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <circle cx="11" cy="4.5" r="2.2" />
            <circle cx="4.5" cy="15" r="2.2" />
            <circle cx="17.5" cy="15" r="2.2" />
            <path d="M11 6.7 6 13M11 6.7 16 13M6.7 15h8.6" />
          </svg>
          <span className={styles.brandName}>MARS</span>
          <span className={styles.brandSub}>ADMET Rapid Screening</span>
        </Link>
        <nav className={styles.nav} aria-label="Page sections">
          <a href="#what">What it does</a>
          <a href="#specimen">See it work</a>
          <a href="#scope">Scope</a>
          <a href="#workspaces">Workspaces</a>
        </nav>
        <div className={styles.spacer} />
        <button className={styles.ghost} type="button" onClick={() => enter("/predict")}>
          Open workspace
        </button>
        {USING_API && status === "anonymous" && (
          <button className={styles.signin} type="button" onClick={() => enter("/settings")}>
            Sign in
          </button>
        )}
      </header>

      <main id="landing-main" tabIndex={-1}>
        <section className={styles.hero}>
          <MoleculeArt />
          <div className={styles.heroIn}>
            <div className={styles.lockup}>
              <svg className={styles.mark} viewBox="0 0 22 22" fill="none" aria-hidden="true">
                <circle cx="11" cy="4.5" r="2.2" />
                <circle cx="4.5" cy="15" r="2.2" />
                <circle cx="17.5" cy="15" r="2.2" />
                <path d="M11 6.7 6 13M11 6.7 16 13M6.7 15h8.6" />
              </svg>
              <div>
                <div className={styles.wordmark} aria-hidden="true">MARS</div>
                <div className={styles.wordSub}>ADMET Rapid Screening</div>
              </div>
            </div>
            <h1 className={styles.tagline}>Know what the model knows.</h1>
            <p className={styles.taglineSub}>ADMET prediction that shows its working.</p>

            <div className={styles.entry}>
              <label id="landing-smiles-label" htmlFor="landing-smiles" className={styles.label}>
                Start with a molecule · SMILES
              </label>
              <InputBar
                id="landing-smiles"
                large
                smiles={smiles}
                onChange={(s) => {
                  setSmiles(s);
                  setNote("");
                }}
                onPredict={predict}
              />
              <div className={styles.chips}>
                <button
                  className={styles.chip}
                  type="button"
                  onClick={() => {
                    setSmiles(EXAMPLE_SMILES);
                    setNote("Example loaded. Press Predict to run it.");
                  }}
                >
                  Use example
                </button>
                <button className={styles.chip} type="button" onClick={() => enter("/predict")}>
                  Draw structure
                </button>
                <button className={styles.chip} type="button" onClick={() => enter("/batch")}>
                  Upload CSV
                </button>
                <span className={styles.chipNote}>Predict and Compare need no account.</span>
              </div>
              <div className={styles.note}>{note || apiNote}</div>
            </div>
          </div>
        </section>

        <div className={styles.wrap}>
          <section id="what" className={styles.sec}>
            <div className={styles.secHead}>
              <div className={styles.secText}>
                <div className={styles.label}>What it does</div>
                <h2 className={styles.h2}>{ML_ENDPOINTS.length} endpoints from one structure.</h2>
                <p className={styles.lede}>
                  Paste a SMILES string or draw a molecule. MARS returns each value with its seed spread, an
                  applicability-domain check and the model that served it, and says so when it cannot answer.
                </p>
              </div>
              <div className={styles.meta}>
                <span>{ML_ENDPOINTS.length} endpoints</span>
                <span>{categories} categories</span>
                <span>5-seed spread</span>
                {generations?.active && <span>{generations.active}</span>}
              </div>
            </div>
            <div className={styles.admet}>
              {ADMET.map((g) => (
                <div key={g.group} className={styles.admetCol}>
                  <div className={styles.admetLetter} aria-hidden="true">{g.label[0]}</div>
                  <div className={styles.admetName}>{g.label}</div>
                  <div className={styles.admetCount}>{g.count === 1 ? "1 endpoint" : `${g.count} endpoints`}</div>
                  <div className={styles.admetShort}>{g.short}</div>
                </div>
              ))}
            </div>
            <p className={styles.fine}>
              Synthetic accessibility is shown separately as a rule-based score. It is computed by rule and is not one of the{" "}
              {ML_ENDPOINTS.length}.
            </p>
          </section>

          <section id="specimen" className={`${styles.sec} ${styles.secRule}`}>
            <div className={styles.secText}>
              <div className={styles.label}>See it work</div>
              <h2 className={styles.h2}>Every number shows its working.</h2>
              <p className={styles.lede}>
                This is the real roster for one example molecule, from the live service. Select a row to see its spread,
                its source and how well the training data covers the molecule.
              </p>
            </div>
            <Specimen />
            <ul className={styles.legend}>
              <li>Every value is mono and the same colour, whatever its size.</li>
              <li>Amber marks out-of-domain; grey marks not returned. Neither recolours the value.</li>
              <li>Hatch means the value did not come from a promoted model.</li>
              <li>The range is the spread across 5 seeds, not a confidence interval.</li>
            </ul>
          </section>

          <section id="scope" className={`${styles.sec} ${styles.secRule}`}>
            <div className={styles.secText}>
              <div className={styles.label}>Scope</div>
              <h2 className={styles.h2}>What a MARS number is not.</h2>
              <p className={styles.lede}>
                MARS has no validated risk threshold and no validated direction of good. So it does not say a molecule is
                safe or risky. It says what the model returned, how far to lean on it, and where it came from.
              </p>
            </div>
            <div className={styles.scope}>
              {SCOPE.map((s) => (
                <div key={s.title} className={styles.scopeItem}>
                  <div className={styles.scopeTitle}>{s.title}</div>
                  <p className={styles.scopeText}>{s.text}</p>
                </div>
              ))}
            </div>
          </section>

          <section id="workspaces" className={`${styles.sec} ${styles.secRule}`}>
            <div className={styles.secHead}>
              <div className={styles.secText}>
                <div className={styles.label}>Workspaces</div>
                <h2 className={styles.h2}>Five workspaces. One keyboard.</h2>
              </div>
              <p className={styles.keys}>
                Press 1 to 5 to switch. <kbd className={styles.kbd}>⌘K</kbd> opens the command palette.
              </p>
            </div>
            <div className={styles.ws}>
              {WORKSPACES.map((w) => (
                <Link key={w.key} to={w.path} className={styles.wsCol} onClick={markLandingSeen}>
                  <div className={styles.wsKey} aria-hidden="true">{w.key}</div>
                  <div className={styles.wsName}>{w.name}</div>
                  <p className={styles.wsText}>{w.text}</p>
                  <div className={styles.wsAcct}>{isGatedPath(w.path) ? "Account" : "No account"}</div>
                </Link>
              ))}
            </div>
          </section>
        </div>

        <section className={styles.closing}>
          <div className={styles.closingEcho} aria-hidden="true">MARS</div>
          <div className={styles.closingIn}>
            <h2 id="landing-smiles2-label" className={styles.h2}>Try a molecule.</h2>
            <InputBar id="landing-smiles2" large smiles={smiles} onChange={setSmiles} onPredict={predict} />
          </div>
        </section>
      </main>

      <footer className={styles.foot}>
        <div className={styles.footIn}>
          <div className={styles.footCols}>
            <div>
              <div className={styles.label}>Data</div>
              <p>One public Therapeutics Data Commons dataset per endpoint, licensed CC BY 4.0. Scaffold split, five cross-validation seeds.</p>
            </div>
            <div>
              <div className={styles.label}>Models</div>
              <p>One XGBoost model per endpoint on fingerprints and RDKit descriptors. A KERMT graph model can serve some endpoints; every row names which model answered.</p>
            </div>
            <div>
              <div className={styles.label}>Your molecules</div>
              <p>Molecules you submit are never used for training. Saved items stay until you delete them.</p>
            </div>
          </div>
          <div className={styles.footBase}>
            <span>Research preview. Not for clinical or regulatory decisions.</span>
            <span className={styles.spacer} />
            {generations?.active && <span className={styles.mono}>{generations.active}</span>}
          </div>
        </div>
      </footer>
    </div>
  );
}
