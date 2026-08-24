import { lazy, Suspense } from "react";
import { Navigate, Routes, Route } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { PageLoading } from "@/components/common/PageLoading";
import { HomePage } from "@/pages/HomePage";
import { useDeveloperMode } from "@/context/DeveloperModeContext";

// HomePage stays eager — it's the landing route, no reason to show a
// loading flash for the very first thing anyone sees. Everything else is
// lazy so the initial bundle doesn't ship five pages nobody may visit.
const ExplorePage = lazy(() => import("@/pages/ExplorePage").then((m) => ({ default: m.ExplorePage })));
const ComparePage = lazy(() => import("@/pages/ComparePage").then((m) => ({ default: m.ComparePage })));
const ShortlistPage = lazy(() => import("@/pages/ShortlistPage").then((m) => ({ default: m.ShortlistPage })));
const LaptopDetailsPage = lazy(() =>
  import("@/pages/LaptopDetailsPage").then((m) => ({ default: m.LaptopDetailsPage }))
);
const DeveloperPage = lazy(() => import("@/pages/DeveloperPage").then((m) => ({ default: m.DeveloperPage })));

function Page({ section, children }: { section: string; children: React.ReactNode }) {
  return (
    <ErrorBoundary section={section}>
      <Suspense fallback={<PageLoading />}>{children}</Suspense>
    </ErrorBoundary>
  );
}

function DeveloperRoute() {
  const { isUnlocked } = useDeveloperMode();
  if (!isUnlocked) return <Navigate to="/" replace />;
  return (
    <Page section="Developer Mode">
      <DeveloperPage />
    </Page>
  );
}

function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route
          path="/"
          element={
            <ErrorBoundary section="the chat">
              <HomePage />
            </ErrorBoundary>
          }
        />
        <Route
          path="/explore"
          element={
            <Page section="Explore">
              <ExplorePage />
            </Page>
          }
        />
        <Route
          path="/compare"
          element={
            <Page section="Compare">
              <ComparePage />
            </Page>
          }
        />
        <Route
          path="/shortlist"
          element={
            <Page section="Shortlist">
              <ShortlistPage />
            </Page>
          }
        />
        <Route
          path="/laptop/:id"
          element={
            <Page section="the laptop details page">
              <LaptopDetailsPage />
            </Page>
          }
        />
        <Route
          path="/developer"
          element={<DeveloperRoute />}
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
