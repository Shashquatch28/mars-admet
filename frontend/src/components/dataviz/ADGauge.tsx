// The applicability-domain gauge — a reading against a reference, not an interval
// (ADR-012). Sibling of IntervalTrack over the same bounded geometry; requires an
// explicit domain. The marker takes the reliability colour of its STATE (amber
// past threshold, neutral inside), never a colour by its position on the axis.
// The marker settles once per endpoint on first open (ADR-013); the track,
// covered zone and threshold are drawn instantly, and under reduced motion the
// marker is placed, not animated.
import { useEffect, useState } from "react";
import styles from "./dataviz.module.css";
import { scalePct } from "./scale";
import type { Endpoint } from "../../types/contracts";

export interface ADGaugeProps {
  endpoint: Endpoint; // identity for the one-time settle
  value: number; // 5-NN Tanimoto distance
  threshold: number; // validated, per endpoint
  domain: readonly [number, number]; // required
  inDomain: boolean; // colours the marker only
}

const settled = new Set<string>();
const prefersReduced =
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function ADGauge({ endpoint, value, threshold, domain, inDomain }: ADGaugeProps) {
  const target = scalePct(value, domain);
  const thrPct = scalePct(threshold, domain);
  const collide = Math.abs(value - threshold) < 0.09;
  const firstTime = !settled.has(endpoint) && !prefersReduced;
  const [left, setLeft] = useState(firstTime ? 0 : target);

  useEffect(() => {
    if (!firstTime) return;
    settled.add(endpoint);
    const id = requestAnimationFrame(() => requestAnimationFrame(() => setLeft(target)));
    return () => cancelAnimationFrame(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint]);

  const mkClass = inDomain ? styles.gmk : `${styles.gmk} ${styles.gmkOod}`;
  const mkColor = inDomain ? "var(--text-secondary)" : "var(--caution)";

  return (
    <div className={styles.gauge}>
      <div className={styles.seclbl}>
        Model coverage<span className={styles.r}>5-NN Tanimoto · ECFP4</span>
      </div>
      <div className={styles.gwrap}>
        <div className={styles.gtrack} />
        <div className={styles.gcov} style={{ width: `${thrPct}%` }} />
        <div className={styles.gthr} style={{ left: `${thrPct}%` }} />
        <div className={styles.gthrlab} style={{ left: `${thrPct}%` }}>
          {threshold.toFixed(2)}
        </div>
        <div
          className={collide ? `${styles.gmklab} ${styles.gmklabBelow}` : styles.gmklab}
          style={{ left: `${target}%` }}
        >
          {value.toFixed(2)}
        </div>
        <div className={mkClass} style={{ left: `${left}%` }} />
      </div>
      <div className={styles.gends}>
        <span>{domain[0].toFixed(2)}</span>
        <span>{domain[1].toFixed(2)}</span>
      </div>
      <div className={styles.glegend}>
        <span className={styles.legItem}>
          <span className={`${styles.sw} ${styles.swCov}`} />covered
        </span>
        <span className={styles.legItem}>
          <span className={`${styles.sw} ${styles.swThr}`} />threshold
        </span>
        <span className={styles.legItem}>
          <span className={`${styles.sw} ${styles.swMk}`} style={{ background: mkColor }} />this
          molecule
        </span>
      </div>
      <p className={styles.gcap}>
        Measures how well this endpoint&rsquo;s training set covers this molecule. It is not a
        statement about the molecule.
      </p>
    </div>
  );
}
