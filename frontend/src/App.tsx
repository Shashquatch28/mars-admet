import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { queryClient } from "./app/queryClient";
import { UiStateProvider } from "./app/uiState";
import { PredictSessionProvider } from "./app/predictSession";
import { AuthSessionProvider } from "./app/authSession";
import { BatchSessionProvider } from "./app/batchSession";
import { SavedMarksProvider } from "./app/savedMarks";
import { Gated } from "./auth/Gated";
import { SettingsWorkspace } from "./workspaces/settings/SettingsWorkspace";
import { AppShell } from "./shell/AppShell";
import { PredictWorkspace } from "./workspaces/predict/PredictWorkspace";
import { StubWorkspace } from "./workspaces/StubWorkspace";
import { BatchWorkspace } from "./workspaces/batch/BatchWorkspace";
import { LibraryWorkspace } from "./workspaces/library/LibraryWorkspace";

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <UiStateProvider>
          <AuthSessionProvider>
            <SavedMarksProvider>
            <PredictSessionProvider>
              <BatchSessionProvider>
              <Routes>
                <Route element={<AppShell />}>
                  <Route index element={<Navigate to="/predict" replace />} />
                  <Route path="/predict" element={<PredictWorkspace />} />
                  <Route path="/batch" element={<Gated name="Batch"><BatchWorkspace /></Gated>} />
                  <Route path="/compare" element={<StubWorkspace name="Compare" />} />
                  <Route path="/library" element={<Gated name="Library"><LibraryWorkspace /></Gated>} />
                  <Route path="/settings" element={<SettingsWorkspace />} />
                  <Route path="*" element={<Navigate to="/predict" replace />} />
                </Route>
              </Routes>
              </BatchSessionProvider>
            </PredictSessionProvider>
            </SavedMarksProvider>
          </AuthSessionProvider>
        </UiStateProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
