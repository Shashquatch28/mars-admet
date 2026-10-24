import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { queryClient } from "./app/queryClient";
import { UiStateProvider } from "./app/uiState";
import { AnnouncerProvider } from "./app/announce";
import { PredictSessionProvider } from "./app/predictSession";
import { AuthSessionProvider } from "./app/authSession";
import { BatchSessionProvider } from "./app/batchSession";
import { SavedMarksProvider } from "./app/savedMarks";
import { Gated } from "./auth/Gated";
import { ForgotPassword } from "./auth/ForgotPassword";
import { ResetPassword } from "./auth/ResetPassword";
import { SettingsWorkspace } from "./workspaces/settings/SettingsWorkspace";
import { AppShell } from "./shell/AppShell";
import { PredictWorkspace } from "./workspaces/predict/PredictWorkspace";
import { BatchWorkspace } from "./workspaces/batch/BatchWorkspace";
import { LibraryWorkspace } from "./workspaces/library/LibraryWorkspace";
import { CompareWorkspace } from "./workspaces/compare/CompareWorkspace";
import { MoleculeWorkspace } from "./workspaces/molecule/MoleculeWorkspace";
import { CompareSessionProvider } from "./app/compareSession";
import { EntryRoute } from "./landing/EntryRoute";
import { LandingPage } from "./landing/LandingPage";

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AnnouncerProvider>
        <UiStateProvider>
          <AuthSessionProvider>
            <SavedMarksProvider>
            <PredictSessionProvider>
              <BatchSessionProvider>
              <CompareSessionProvider>
              <Routes>
                {/* The front door sits outside the shell: no rail, no status bar (ADR-046). */}
                <Route path="/" element={<EntryRoute />} />
                <Route path="/welcome" element={<LandingPage />} />
                <Route element={<AppShell />}>
                  <Route path="/predict" element={<PredictWorkspace />} />
                  <Route path="/batch" element={<Gated name="Batch"><BatchWorkspace /></Gated>} />
                  <Route path="/compare" element={<CompareWorkspace />} />
                  <Route path="/library" element={<Gated name="Library"><LibraryWorkspace /></Gated>} />
                  <Route path="/molecule" element={<MoleculeWorkspace />} />
                  <Route path="/settings" element={<SettingsWorkspace />} />
                  <Route path="/forgot-password" element={<ForgotPassword />} />
                  <Route path="/reset-password" element={<ResetPassword />} />
                  <Route path="*" element={<Navigate to="/predict" replace />} />
                </Route>
              </Routes>
              </CompareSessionProvider>
              </BatchSessionProvider>
            </PredictSessionProvider>
            </SavedMarksProvider>
          </AuthSessionProvider>
        </UiStateProvider>
        </AnnouncerProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
