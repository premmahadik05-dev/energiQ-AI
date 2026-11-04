import type { ReactNode } from 'react';
import { Link, Navigate, Outlet, useLocation } from 'react-router-dom';
import { Loading } from '../components/ui/feedback';
import { safeInternalLink } from '../lib/links';
import type { Role } from '../api/types';
import { useAuth } from './AuthContext';

/** Everything below requires a signed-in user; anonymous visitors are sent to /login and returned afterwards. */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === 'loading') return <Loading label="Checking your session" />;
  if (status === 'anonymous') return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  return <Outlet />;
}

/**
 * Login and register: signed-in users go straight to the app. Signing in flips the status to "authenticated" before
 * the login page's own redirect runs, so this guard is what sends the user back to the page they originally asked
 * for (RequireAuth stored it in the navigation state). Only app-internal paths are followed.
 */
export function PublicOnly() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === 'loading') return <Loading label="Checking your session" />;
  if (status === 'authenticated') {
    const from = (location.state as { from?: unknown } | null)?.from;
    return <Navigate to={(typeof from === 'string' && safeInternalLink(from)) || '/'} replace />;
  }
  return <Outlet />;
}

export function RequireRole({ roles, children }: { roles: Role[]; children?: ReactNode }) {
  const { user } = useAuth();
  if (!user || !roles.includes(user.role)) {
    return (
      <div className="mx-auto max-w-lg p-8" role="alert">
        <h1 className="text-xl">Access denied</h1>
        <p className="mt-2 text-ink-2">
          This page needs the <strong>{roles.join(' or ')}</strong> role. Your account has the <strong>{user?.role ?? 'unknown'}</strong> role.
        </p>
        <Link to="/" className="btn-secondary mt-4">
          Back to the dashboard
        </Link>
      </div>
    );
  }
  return children ? <>{children}</> : <Outlet />;
}

/** Renders its children only for roles that may change data (analyst, admin). */
export function WriteOnly({ children }: { children: ReactNode }) {
  const { canWrite } = useAuth();
  return canWrite ? <>{children}</> : null;
}
