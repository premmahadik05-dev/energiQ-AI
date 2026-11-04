import type { ReactNode } from 'react';
import { AuthProvider } from './auth/AuthContext';
import { DatasetProvider } from './state/DatasetContext';
import { JobsProvider } from './state/JobsContext';
import { ToastProvider } from './state/ToastContext';

/** Provider order matters: auth -> toasts -> jobs (uses both) -> datasets (uses jobs). */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <ToastProvider>
        <JobsProvider>
          <DatasetProvider>{children}</DatasetProvider>
        </JobsProvider>
      </ToastProvider>
    </AuthProvider>
  );
}
