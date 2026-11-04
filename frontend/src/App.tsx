import { lazy, Suspense, type ComponentType } from 'react';
import { Route, Routes, useLocation } from 'react-router-dom';
import { PublicOnly, RequireAuth, RequireRole } from './auth/guards';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Loading } from './components/ui/feedback';
import { AppShell } from './layout/AppShell';

// Every page is its own chunk; Recharts only loads with the first page that draws a chart.
const lazyPage = <K extends string>(loader: () => Promise<Record<K, ComponentType>>, name: K) => lazy(async () => ({ default: (await loader())[name] }));

const LoginPage = lazyPage(() => import('./pages/AuthPages'), 'LoginPage');
const RegisterPage = lazyPage(() => import('./pages/AuthPages'), 'RegisterPage');
const DashboardPage = lazyPage(() => import('./pages/DashboardPage'), 'DashboardPage');
const DatasetsPage = lazyPage(() => import('./pages/DatasetsPage'), 'DatasetsPage');
const DatasetDetailPage = lazyPage(() => import('./pages/DatasetDetailPage'), 'DatasetDetailPage');
const ForecastPage = lazyPage(() => import('./pages/ForecastPage'), 'ForecastPage');
const ModelsPage = lazyPage(() => import('./pages/ModelsPage'), 'ModelsPage');
const AnomaliesPage = lazyPage(() => import('./pages/AnomaliesPage'), 'AnomaliesPage');
const ExplainPage = lazyPage(() => import('./pages/ExplainPage'), 'ExplainPage');
const OptimizePage = lazyPage(() => import('./pages/OptimizePage'), 'OptimizePage');
const BenchmarkPage = lazyPage(() => import('./pages/BenchmarkPage'), 'BenchmarkPage');
const AdminPage = lazyPage(() => import('./pages/AdminPage'), 'AdminPage');
const NotificationsPage = lazyPage(() => import('./pages/NotificationsPage'), 'NotificationsPage');
const JobsPage = lazyPage(() => import('./pages/JobsPage'), 'JobsPage');
const NotFoundPage = lazyPage(() => import('./pages/NotFoundPage'), 'NotFoundPage');

export function AppRoutes() {
  const location = useLocation();
  return (
    <ErrorBoundary resetKey={location.pathname}>
      <Suspense fallback={<Loading label="Loading page" />}>
        <Routes>
          <Route element={<PublicOnly />}>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
          </Route>
          <Route element={<RequireAuth />}>
            <Route element={<AppShell />}>
              <Route index element={<DashboardPage />} />
              <Route path="datasets" element={<DatasetsPage />} />
              <Route path="datasets/:id" element={<DatasetDetailPage />} />
              <Route path="forecast" element={<ForecastPage />} />
              <Route path="models" element={<ModelsPage />} />
              <Route path="models/:modelId" element={<ModelsPage />} />
              <Route path="anomalies" element={<AnomaliesPage />} />
              <Route path="explain" element={<ExplainPage />} />
              <Route path="optimize" element={<OptimizePage />} />
              <Route path="benchmark" element={<BenchmarkPage />} />
              <Route path="notifications" element={<NotificationsPage />} />
              <Route path="jobs" element={<JobsPage />} />
              <Route element={<RequireRole roles={['admin']} />}>
                <Route path="admin" element={<AdminPage />} />
              </Route>
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Route>
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}
