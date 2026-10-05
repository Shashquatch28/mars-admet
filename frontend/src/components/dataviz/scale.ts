// Shared 0..1-style mapping for the bounded marks. IntervalTrack and ADGauge are
// siblings over this geometry (ADR-012): both require an explicit domain and
// neither can render without a real axis.
export function scalePct(value: number, domain: readonly [number, number]): number {
  const [d0, d1] = domain;
  if (d1 === d0) return 0;
  const t = ((value - d0) / (d1 - d0)) * 100;
  return Math.max(0, Math.min(100, t));
}
