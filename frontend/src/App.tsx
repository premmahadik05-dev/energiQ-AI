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
const SocietyOverviewPage = lazyPage(() => import('./pages/society/SocietyOverviewPage'), 'SocietyOverviewPage');
const ConsumptionPage = lazyPage(() => import('./pages/society/ConsumptionPage'), 'ConsumptionPage');
const SocietyForecastPage = lazyPage(() => import('./pages/society/SocietyForecastPage'), 'SocietyForecastPage');
const CompareCommunitiesPage = lazyPage(() => import('./pages/society/CompareCommunitiesPage'), 'CompareCommunitiesPage');
const BuildingsPage = lazyPage(() => import('./pages/society/BuildingsPage'), 'BuildingsPage');
const FacilitiesPage = lazyPage(() => import('./pages/society/FacilitiesPage'), 'FacilitiesPage');
const PeaksCostPage = lazyPage(() => import('./pages/society/PeaksCostPage'), 'PeaksCostPage');
const SocietyAlertsPage = lazyPage(() => import('./pages/society/SocietyAlertsPage'), 'SocietyAlertsPage');
const SocietyRecommendationsPage = lazyPage(() => import('./pages/society/SocietyRecommendationsPage'), 'SocietyRecommendationsPage');
const SocietyReportsPage = lazyPage(() => import('./pages/society/SocietyReportsPage'), 'SocietyReportsPage');
const DataSourcesPage = lazyPage(() => import('./pages/society/DataSourcesPage'), 'DataSourcesPage');
const SocietyAdminPage = lazyPage(() => import('./pages/society/SocietyAdminPage'), 'SocietyAdminPage');
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
              <Route index element={<SocietyOverviewPage />} />
              <Route path="consumption" element={<ConsumptionPage />} />
              <Route path="forecasting" element={<SocietyForecastPage />} />
              <Route path="compare" element={<CompareCommunitiesPage />} />
              <Route path="buildings" element={<BuildingsPage />} />
              <Route path="facilities" element={<FacilitiesPage />} />
              <Route path="cost" element={<PeaksCostPage />} />
              <Route path="alerts" element={<SocietyAlertsPage />} />
              <Route path="recommendations" element={<SocietyRecommendationsPage />} />
              <Route path="reports" element={<SocietyReportsPage />} />
              <Route path="data-sources" element={<DataSourcesPage />} />
              <Route path="notifications" element={<NotificationsPage />} />
              <Route path="jobs" element={<JobsPage />} />
              <Route element={<RequireRole roles={['admin']} />}>
                <Route path="admin" element={<AdminPage />} />
                <Route path="society-admin" element={<SocietyAdminPage />} />
              </Route>
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Route>
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}
