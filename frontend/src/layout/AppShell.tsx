import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { Icon, Logo } from '../components/ui/Icon';
import { Topbar } from './Topbar';

interface NavItem {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
}

const NAV: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: 'dashboard', end: true },
  { to: '/datasets', label: 'Datasets', icon: 'database' },
  { to: '/forecast', label: 'Forecast', icon: 'forecast' },
  { to: '/models', label: 'Models', icon: 'model' },
  { to: '/anomalies', label: 'Anomalies', icon: 'alert' },
  { to: '/explain', label: 'Explainability', icon: 'explain' },
  { to: '/optimize', label: 'Optimisation', icon: 'coin' },
  { to: '/benchmark', label: 'Benchmark', icon: 'benchmark' },
  { to: '/jobs', label: 'Jobs', icon: 'jobs' },
];

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const { hasRole } = useAuth();
  const items = hasRole('admin') ? [...NAV, { to: '/admin', label: 'Admin', icon: 'admin' }] : NAV;
  return (
    <nav aria-label="Main">
      <ul className="space-y-0.5">
        {items.map((n) => (
          <li key={n.to}>
            <NavLink
              to={n.to}
              end={n.end}
              onClick={onNavigate}
              className={({ isActive }) =>
                `flex min-h-[40px] items-center gap-3 rounded px-3 text-sm font-medium ${isActive ? 'bg-accent-soft text-accent' : 'text-ink-2 hover:bg-sunken hover:text-ink'}`
              }
            >
              <Icon name={n.icon} className="h-[18px] w-[18px]" />
              {n.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function AppShell() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => {
    setOpen(false);
    mainRef.current?.focus({ preventScroll: true });
    window.scrollTo?.({ top: 0 });
  }, [location.pathname]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[15rem_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[70] focus:rounded focus:bg-accent focus:px-3 focus:py-2 focus:text-accent-ink">
        Skip to content
      </a>
      <aside className="hidden border-r border-line bg-surface lg:block">
        <div className="sticky top-0 flex h-screen flex-col gap-6 overflow-y-auto p-4">
          <div className="flex items-center gap-2.5 px-1 pt-1">
            <Logo />
            <span className="text-lg font-semibold tracking-tight">EnergiQ AI</span>
          </div>
          <NavList />
        </div>
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <button type="button" aria-label="Close navigation" className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <div className="relative flex h-full w-64 max-w-[80vw] flex-col gap-6 overflow-y-auto bg-surface p-4 shadow-xl">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2.5">
                <Logo />
                <span className="text-lg font-semibold">EnergiQ AI</span>
              </span>
              <button type="button" className="btn-ghost !px-2" onClick={() => setOpen(false)} aria-label="Close navigation">
                <Icon name="close" />
              </button>
            </div>
            <NavList onNavigate={() => setOpen(false)} />
          </div>
        </div>
      )}
      <div className="flex min-w-0 flex-col">
        <Topbar onMenu={() => setOpen(true)} />
        <main id="main" ref={mainRef} tabIndex={-1} className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-6 outline-none sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
