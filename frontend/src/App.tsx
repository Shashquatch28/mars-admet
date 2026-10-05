import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { queryClient } from "./app/queryClient";
import { UiStateProvider } from "./app/uiState";
import { AppShell } from "./shell/AppShell";
import { PredictWorkspace } from "./workspaces/predict/PredictWorkspace";
import { StubWorkspace } from "./workspaces/StubWorkspace";

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <UiStateProvider>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<Navigate to="/predict" replace />} />
              <Route path="/predict" element={<PredictWorkspace />} />
              <Route path="/batch" element={<StubWorkspace name="Batch" />} />
              <Route path="/compare" element={<StubWorkspace name="Compare" />} />
              <Route path="/library" element={<StubWorkspace name="Library" />} />
              <Route path="/settings" element={<StubWorkspace name="Settings" />} />
              <Route path="*" element={<Navigate to="/predict" replace />} />
            </Route>
          </Routes>
        </UiStateProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
