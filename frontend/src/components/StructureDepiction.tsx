// A 2D drawing of a molecule: plain line art in one ink, nothing marked (ADR-039). Standalone: it takes a SMILES and draws
// it, and knows nothing about predictions, endpoints or any value, so nothing it shows can depend on one. The drawing comes
// from the service as black line art; the only change made here is putting that one ink in a token's colour.
//
// States are words, never a spinner that counts or a shimmer: drawing, drawn, or why it could not be drawn.
import { useMemo } from "react";
import styles from "./structureDepiction.module.css";
import { ApiError, USING_API } from "../data/client";
import { useDepiction } from "../data/useDepiction";
import { DEPICTION_NOTE, depictionFailure, inkSvg, isDrawable, svgDataUrl } from "../domain/depiction";

export function StructureDepiction({
  smiles,
  ink = "--text-secondary",
  label = "Structure",
  note = true,
  className,
}: {
  /** What to draw. Null or blank renders nothing: there is no molecule yet. */
  smiles: string | null | undefined;
  /** The CSS custom property whose colour the line art takes (a token, never a literal). */
  ink?: string;
  /** Names the drawing for assistive technology and for the caption. */
  label?: string;
  /** Print the one-line statement of what the drawing is under it. */
  note?: boolean;
  className?: string;
}) {
  const q = useDepiction(smiles);
  const color = useMemo(
    () => (typeof document === "undefined" ? "" : getComputedStyle(document.documentElement).getPropertyValue(ink)),
    [ink],
  );
  const src = useMemo(() => (q.data && isDrawable(q.data) ? svgDataUrl(inkSvg(q.data, color)) : null), [q.data, color]);

  if (!USING_API || !smiles || !smiles.trim()) return null;

  let body;
  if (q.isPending) body = <p className={styles.state}>Drawing the structure…</p>;
  else if (q.isError)
    body = (
      <p className={styles.state}>
        {depictionFailure(q.error instanceof ApiError ? q.error.status : 0, q.error.message)}
      </p>
    );
  else if (!src) body = <p className={styles.state}>The service sent something that is not a drawing, so none is shown.</p>;
  else body = <img className={styles.img} src={src} alt={`${label}: 2D drawing of ${smiles.trim()}`} width={320} height={220} />;

  return (
    <figure className={`${styles.fig} ${className ?? ""}`}>
      {body}
      {note && src && <figcaption className={styles.note}>{DEPICTION_NOTE}</figcaption>}
    </figure>
  );
}
