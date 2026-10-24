// Decorative line art for the landing hero: a skeletal structure drawn large and cropped by the frame, over
// a dot grid. It is a texture, not data: it is not the example molecule's real depiction, it is not coloured
// or sized by anything about a molecule, and it maps nothing to atoms or endpoints (ADR-039, ADR-046).
// Hidden from assistive technology.
import styles from "./landing.module.css";

export function MoleculeArt() {
  return (
    <svg
      className={styles.art}
      aria-hidden="true"
      focusable="false"
      viewBox="-300 -330 600 840"
      preserveAspectRatio="xMaxYMin meet"
    >
      <defs>
        <pattern id="landing-dots" x="0" y="0" width="24" height="24" patternUnits="userSpaceOnUse">
          <circle cx="1" cy="1" r="1" className={styles.artDot} />
        </pattern>
      </defs>
      <rect x="-300" y="-330" width="600" height="840" fill="url(#landing-dots)" />
      <g className={styles.artRings}>
        <circle cx="0" cy="0" r="210" />
        <circle cx="0" cy="0" r="320" />
        <circle cx="0" cy="0" r="440" />
      </g>
      <g className={styles.artBonds}>
        <path d="M0 -120 L104 -60 L104 60 L0 120 L-104 60 L-104 -60 Z" />
        <path d="M90 -40 L90 40" />
        <path d="M-8.6 98.9 L-81.4 56.9" />
        <path d="M-81.4 -56.9 L-8.6 -98.9" />
        <path d="M0 -120 L0 -224" />
        <path d="M0 120 L0 228" />
        <path d="M10 245 L104 300" />
        <path d="M98 306 L98 404" />
        <path d="M110 306 L110 404" />
        <path d="M104 300 L208 240" />
      </g>
      <g className={styles.artLabels} textAnchor="middle">
        <text x="0" y="-238">OH</text>
        <text x="0" y="252">NH</text>
        <text x="104" y="438">O</text>
      </g>
      <g className={styles.artNodes}>
        <circle cx="0" cy="-120" r="4" />
        <circle cx="104" cy="60" r="4" />
        <circle cx="-104" cy="60" r="4" />
      </g>
    </svg>
  );
}
