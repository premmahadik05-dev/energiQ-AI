import type { ReactNode } from 'react';
import { AuthProvider } from './auth/AuthContext';
import { JobsProvider } from './state/JobsContext';
import { SocietyProvider } from './state/SocietyContext';
import { ToastProvider } from './state/ToastContext';

/** Provider order matters: auth -> toasts -> jobs (uses both) -> societies (uses jobs). */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <ToastProvider>
        <JobsProvider>
          <SocietyProvider>{children}</SocietyProvider>
        </JobsProvider>
      </ToastProvider>
    </AuthProvider>
  );
}
