// Open the browser's print dialog for one molecule's report. "Save as PDF" in that dialog is the PDF
// export (ADR-029): no PDF library, no second copy of the roster logic on the server. The report is
// mounted for the duration of the print and removed afterwards.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { PrintReport } from "./PrintReport";
import type { ExportMolecule } from "../../domain/exportCsv";
import { buildReport, type ReportModel } from "../../domain/report";
import { useGenerations } from "../../data/useGenerations";
import { ApiError, USING_API, fetchDepiction } from "../../data/client";
import { depictionKey } from "../../data/useDepiction";
import { depictionFailure, isDrawable, type ReportStructure } from "../../domain/depiction";

// A report waits this long for its drawing, then prints without it and says so: a slow service never blocks the print dialog.
const DRAWING_WAIT_MS = 6000;

export function usePrintReport(): { print: (m: ExportMolecule) => void; element: ReactNode } {
  const [model, setModel] = useState<ReportModel | null>(null);

  // The dagger needs to know which endpoints the deployment routes to KERMT (GET /generations).
  const kermtEndpoints = useGenerations()?.kermt_endpoints;
  const qc = useQueryClient();
  const print = useCallback(
    (m: ExportMolecule) => {
      void (async () => {
        const smiles = m.response?.smiles_standardized?.trim();
        let structure: ReportStructure | null = null;
        if (smiles && !m.error) {
          if (!USING_API) structure = { kind: "unavailable", reason: "No API is configured." };
          else {
            try {
              const svg = await Promise.race([
                qc.fetchQuery({ queryKey: depictionKey(smiles), queryFn: () => fetchDepiction(smiles), staleTime: Infinity }),
                new Promise<never>((_, reject) => setTimeout(() => reject(new Error("timed out")), DRAWING_WAIT_MS)),
              ]);
              structure = isDrawable(svg)
                ? { kind: "drawn", svg }
                : { kind: "unavailable", reason: "The service sent something that is not a drawing." };
            } catch (e) {
              structure = {
                kind: "unavailable",
                reason: e instanceof ApiError ? depictionFailure(e.status, e.message) : "The drawing was not ready in time.",
              };
            }
          }
        }
        setModel(buildReport(m, new Date(), kermtEndpoints ?? [], structure));
      })();
    },
    [kermtEndpoints, qc],
  );

  useEffect(() => {
    if (!model) return;
    const done = () => setModel(null);
    window.addEventListener("afterprint", done, { once: true });
    window.print();
    return () => window.removeEventListener("afterprint", done);
  }, [model]);

  return { print, element: model ? <PrintReport model={model} /> : null };
}
