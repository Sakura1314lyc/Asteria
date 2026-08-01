import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router";
import { AppShell } from "./components/AppShell";
import { LoadingState } from "./components/Ui";

const DashboardPage = lazy(() =>
  import("./pages/DashboardPage").then((module) => ({
    default: module.DashboardPage
  }))
);
const DocumentsPage = lazy(() =>
  import("./pages/DocumentsPage").then((module) => ({
    default: module.DocumentsPage
  }))
);
const EvidencePage = lazy(() =>
  import("./pages/EvidencePage").then((module) => ({
    default: module.EvidencePage
  }))
);
const LibraryPage = lazy(() =>
  import("./pages/LibraryPage").then((module) => ({
    default: module.LibraryPage
  }))
);
const GlobalLibraryPage = lazy(() =>
  import("./pages/GlobalLibraryPage").then((module) => ({
    default: module.GlobalLibraryPage
  }))
);
const MapPage = lazy(() =>
  import("./pages/MapPage").then((module) => ({
    default: module.MapPage
  }))
);
const NotFoundPage = lazy(() =>
  import("./pages/NotFoundPage").then((module) => ({
    default: module.NotFoundPage
  }))
);
const ProjectLayout = lazy(() =>
  import("./pages/ProjectLayout").then((module) => ({
    default: module.ProjectLayout
  }))
);
const ProjectOverviewPage = lazy(() =>
  import("./pages/ProjectOverviewPage").then((module) => ({
    default: module.ProjectOverviewPage
  }))
);
const ProjectsPage = lazy(() =>
  import("./pages/ProjectsPage").then((module) => ({
    default: module.ProjectsPage
  }))
);
const ReportsPage = lazy(() =>
  import("./pages/ReportsPage").then((module) => ({
    default: module.ReportsPage
  }))
);
const RunPage = lazy(() =>
  import("./pages/RunPage").then((module) => ({
    default: module.RunPage
  }))
);
const ScreeningPage = lazy(() =>
  import("./pages/ScreeningPage").then((module) => ({
    default: module.ScreeningPage
  }))
);
const SettingsPage = lazy(() =>
  import("./pages/SettingsPage").then((module) => ({
    default: module.SettingsPage
  }))
);
const ChatPage = lazy(() =>
  import("./pages/ChatPage").then((module) => ({
    default: module.ChatPage
  }))
);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: (count, error) => {
        const status =
          typeof error === "object" && error && "status" in error
            ? Number(error.status)
            : 0;
        return status >= 400 && status < 500 ? false : count < 2;
      }
    }
  }
});

export function App() {
  const basename = window.location.pathname.startsWith("/app") ? "/app" : "/";
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename={basename}>
        <Suspense fallback={<LoadingState label="正在打开页面" />}>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<DashboardPage />} />
              <Route path="projects" element={<ProjectsPage />} />
              <Route path="library" element={<GlobalLibraryPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="projects/:projectId" element={<ProjectLayout />}>
                <Route index element={<ProjectOverviewPage />} />
                <Route path="library" element={<LibraryPage />} />
                <Route path="screening" element={<ScreeningPage />} />
                <Route path="evidence" element={<EvidencePage />} />
                <Route path="map" element={<MapPage />} />
                <Route path="documents" element={<DocumentsPage />} />
                <Route path="reports" element={<ReportsPage />} />
                <Route path="chat" element={<ChatPage />} />
                <Route path="runs/:runId" element={<RunPage />} />
              </Route>
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
