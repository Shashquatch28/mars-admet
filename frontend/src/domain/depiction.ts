// The 2D structure drawing, as the screen and the printed report show it (ADR-039). Pure and tested.
//
// A drawing says what a molecule looks like and nothing about it. The service draws plain black line art (one ink, no
// element colours, no highlighted atom or bond, no labels); the only thing the client does to it is put that one ink in
// a token's colour. Nothing here colours, marks or scales anything by a value, and nothing is drawn from a prediction.

export const DEPICTION_NOTE =
  "RDKit drawing of the standardized structure. Plain line art: no atom or bond is marked, and the drawing says nothing about any prediction.";

/** The service sent something that is a drawing and only a drawing. A guard, not a sanitiser: the SVG is shown through an <img>, where nothing in it can run. */
export function isDrawable(svg: string): boolean {
  const s = svg.trimStart();
  return s.startsWith("<svg") && s.length < 2_000_000 && !/<script|<foreignObject|<iframe|<object|<embed|\son[a-z]+\s*=/i.test(s);
}

/** A colour that is safe to write into the SVG text in place of the black: a hex colour or an rgb() / rgba() triple, nothing else. */
export function isInk(color: string): boolean {
  return /^#[0-9a-f]{3,8}$/i.test(color) || /^rgba?\(\s*\d{1,3}\s*(,\s*\d{1,3}\s*){2}(,\s*[\d.]+\s*)?\)$/i.test(color);
}

/** The drawing with its one ink (the black RDKit's black-and-white palette writes for every stroke and fill) replaced by `color`. An unusable `color` leaves the black as it came. */
export function inkSvg(svg: string, color: string): string {
  const c = color.trim();
  return isInk(c) ? svg.replace(/#000000/gi, c) : svg;
}

/** The drawing as an `<img>` source. A data URL: no object URL to revoke, and it prints. */
export function svgDataUrl(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

/** Why a drawing is missing, in words. Every message says nothing was drawn; none is about the molecule's values. */
export function depictionFailure(status: number, message: string): string {
  if (status === 501) return "The service has no RDKit, so it cannot draw structures.";
  if (status === 422) return `This structure could not be drawn: ${message.replace(/\.$/, "")}.`;
  if (status === 429) return "Too many drawings were requested at once. Try again in a minute.";
  if (status === 0) return "The API is unreachable, so the structure was not drawn.";
  return `The structure could not be drawn (${status}).`;
}

export type ReportStructure = { kind: "drawn"; svg: string } | { kind: "unavailable"; reason: string };

/** Printed under the report's fixed statements when a drawing is on the page. */
export const STRUCTURE_STATEMENT =
  "The structure drawing is plain line art of the standardized molecule, drawn by RDKit. No atom or bond is marked, and the drawing says nothing about any value in this report.";

/** Printed instead when the service could not draw one: the report says what is missing and why, rather than leaving a gap. */
export const structureMissingStatement = (reason: string): string => `Not included: a 2D structure drawing. ${reason.replace(/\.$/, "")}.`;
