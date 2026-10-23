// The only file that imports Ketcher. StructureEditor loads this module with a dynamic import(), so
// ketcher-react, ketcher-standalone (Indigo as WebAssembly) and Ketcher's stylesheet stay out of the main
// bundle and are fetched the first time the panel opens (ADR-035; tests/structureEditorGuard.test.ts
// enforces both halves). Ketcher draws its own interior and is the one third-party surface in the app.
import { useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import { Editor } from "ketcher-react";
import { StandaloneStructServiceProvider } from "ketcher-standalone/dist/binaryWasmNoRender";
import type { Ketcher } from "ketcher-core";
import "ketcher-react/dist/index.css";

// One provider for the page's lifetime: it owns the Indigo worker, which is expensive to start.
const structServiceProvider = new StandaloneStructServiceProvider();

// MARS predicts one molecule from a SMILES string. Tools for reactions, R-groups, shapes, text, monomers and the
// 3D viewer would draw things that cannot become a prediction; the help/about links leave the app. Hidden, not
// disabled, so no control implies a capability the pipeline lacks (AGENTS never-do #5's reasoning).
const HIDDEN = [
  "analyse", "recognize", "miew", "settings", "help", "about", "fullscreen",
  "arrows", "reaction-plus", "reaction-mapping-tools", "rgroup", "shape", "text", "sgroup", "create-monomer",
] as const;
const BUTTONS = Object.fromEntries(HIDDEN.map((name) => [name, { hidden: true }]));

interface Props {
  onReady: (ketcher: Ketcher) => void;
  onError: (message: string) => void;
}

// Ketcher's <Editor> does not survive React.StrictMode's development-only mount, unmount, mount: its cleanup from the
// first mount tears down the instance the second mount just built ("couldn't find ketcher instance"). So the editor
// is rendered into a root of its own, created from an effect, and StrictMode does not reach inside it. In production
// there is one mount either way.
export default function KetcherCanvas({ onReady, onError }: Props) {
  const slot = useRef<HTMLDivElement>(null);
  // Held in refs so a re-render of the panel does not rebuild the editor.
  const ready = useRef(onReady);
  const failed = useRef(onError);
  ready.current = onReady;
  failed.current = onError;

  useEffect(() => {
    const el = document.createElement("div");
    el.style.cssText = "width:100%;height:100%";
    slot.current?.appendChild(el);
    const root = createRoot(el);
    root.render(
      <Editor
        staticResourcesUrl={import.meta.env.BASE_URL}
        structServiceProvider={structServiceProvider}
        buttons={BUTTONS}
        disableMacromoleculesEditor
        errorHandler={(message) => failed.current(message)}
        onInit={(k) => ready.current(k)}
      />,
    );
    return () => {
      // Not during React's own commit: unmounting another root there is refused.
      setTimeout(() => {
        root.unmount();
        el.remove();
      }, 0);
    };
  }, []);

  return <div ref={slot} style={{ width: "100%", height: "100%" }} />;
}
