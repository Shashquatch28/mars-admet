// Open the browser's print dialog for one molecule's report. "Save as PDF" in that dialog is the PDF
// export (ADR-029): no PDF library, no second copy of the roster logic on the server. The report is
// mounted for the duration of the print and removed afterwards.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { PrintReport } from "./PrintReport";
import type { ExportMolecule } from "../../domain/exportCsv";
import { buildReport, type ReportModel } from "../../domain/report";

export function usePrintReport(): { print: (m: ExportMolecule) => void; element: ReactNode } {
  const [model, setModel] = useState<ReportModel | null>(null);

  const print = useCallback((m: ExportMolecule) => setModel(buildReport(m)), []);

  useEffect(() => {
    if (!model) return;
    const done = () => setModel(null);
    window.addEventListener("afterprint", done, { once: true });
    window.print();
    return () => window.removeEventListener("afterprint", done);
  }, [model]);

  return { print, element: model ? <PrintReport model={model} /> : null };
}
