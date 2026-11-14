import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { pageTitle } from '../lib/pageTitle';
import { Notice } from '../components/ui/feedback';
import { Icon, Logo } from '../components/ui/Icon';
import { Topbar } from './Topbar';

interface NavItem {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
}

interface NavGroup {
  heading: string;
  items: NavItem[];
}

const SOCIETY_NAV: NavItem[] = [
  { to: '/', label: 'Society overview', icon: 'building', end: true },
  { to: '/compare', label: 'Compare communities', icon: 'benchmark' },
  { to: '/consumption', label: 'Consumption', icon: 'chart' },
  { to: '/forecasting', label: 'Forecasting', icon: 'forecast' },
  { to: '/buildings', label: 'Buildings', icon: 'dashboard' },
  { to: '/facilities', label: 'Common facilities', icon: 'plug' },
  { to: '/cost', label: 'Cost and peaks', icon: 'coin' },
  { to: '/alerts', label: 'Alerts', icon: 'alert' },
  { to: '/recommendations', label: 'Recommendations', icon: 'bulb' },
  { to: '/reports', label: 'Reports', icon: 'report' },
  { to: '/data-sources', label: 'Data sources', icon: 'info' },
];

const SYSTEM_NAV: NavItem[] = [{ to: '/jobs', label: 'Jobs', icon: 'jobs' }];

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const { hasRole } = useAuth();
  const admin = hasRole('admin');
  const groups: NavGroup[] = [
    { heading: 'Residential society', items: admin ? [...SOCIETY_NAV, { to: '/society-admin', label: 'Society admin', icon: 'user' }] : SOCIETY_NAV },
    { heading: 'System', items: admin ? [...SYSTEM_NAV, { to: '/admin', label: 'Admin', icon: 'admin' }] : SYSTEM_NAV },
  ];
  return (
    <nav aria-label="Main" className="space-y-5">
      {groups.map((g) => (
        <div key={g.heading}>
          <p className="px-3 pb-1.5 text-[12.5px] font-medium text-nav-muted" id={`nav-${g.heading.replace(/\W+/g, '-').toLowerCase()}`}>
            {g.heading}
          </p>
          <ul className="space-y-0.5" aria-labelledby={`nav-${g.heading.replace(/\W+/g, '-').toLowerCase()}`}>
            {g.items.map((n) => (
              <li key={n.to}>
                <NavLink
                  to={n.to}
                  end={n.end}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    `relative flex min-h-[38px] items-center gap-3 rounded-md px-3 text-[14px] font-medium transition-colors ${isActive ? 'bg-nav-active text-nav-ink-strong before:absolute before:bottom-2 before:left-0 before:top-2 before:w-[3px] before:rounded-full before:bg-nav-bar' : 'text-nav-ink hover:bg-nav-hover hover:text-nav-ink-strong'}`
                  }
                >
                  {({ isActive }) => (
                    <>
                      <Icon name={n.icon} className={`h-[18px] w-[18px] ${isActive ? 'text-nav-bar' : ''}`} />
                      {n.label}
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export function AppShell() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const { user } = useAuth();
  const mainRef = useRef<HTMLElement>(null);
  // set by the registration page: a one-time confirmation on the first screen after the account was created
  const [welcomeSeen, setWelcomeSeen] = useState(false);
  const welcome = (location.state as { welcome?: boolean } | null)?.welcome === true && !welcomeSeen && user !== null;

  useEffect(() => {
    document.title = pageTitle(location.pathname);
  }, [location.pathname]);

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
      <aside className="hidden border-r border-nav-line bg-nav-bg lg:block">
        <div className="nav-scroll sticky top-0 flex h-screen flex-col gap-7 overflow-y-auto px-3 py-5">
          <div className="flex items-center gap-2.5 px-2">
            <Logo className="h-8 w-8" />
            <span className="text-[19px] font-semibold tracking-tight text-nav-ink-strong">EnergiQ AI</span>
          </div>
          <NavList />
        </div>
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <button type="button" aria-label="Close navigation" className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <div className="nav-scroll relative flex h-full w-64 max-w-[80vw] flex-col gap-6 overflow-y-auto border-r border-nav-line bg-nav-bg px-3 py-5 shadow-xl">
            <div className="flex items-center justify-between px-2">
              <span className="flex items-center gap-2.5">
                <Logo className="h-8 w-8" />
                <span className="text-[19px] font-semibold tracking-tight text-nav-ink-strong">EnergiQ AI</span>
              </span>
              <button type="button" className="inline-flex min-h-[36px] items-center rounded-md px-2 text-nav-ink hover:bg-nav-hover hover:text-nav-ink-strong" onClick={() => setOpen(false)} aria-label="Close navigation">
                <Icon name="close" />
              </button>
            </div>
            <NavList onNavigate={() => setOpen(false)} />
          </div>
        </div>
      )}
      <div className="flex min-w-0 flex-col">
        <Topbar onMenu={() => setOpen(true)} />
        <main id="main" ref={mainRef} tabIndex={-1} className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-7 outline-none sm:px-6 lg:px-9">
          {welcome && (
            <div className="mb-6">
              <Notice tone="good" role="status" title="Account created" onDismiss={() => setWelcomeSeen(true)}>
                {user?.role === 'viewer'
                  ? 'You are signed in with the viewer role: you can open every page, but changes are disabled.'
                  : `You are signed in with the ${user?.role} role: you can acknowledge alerts and create reports.`}
              </Notice>
            </div>
          )}
          <Outlet />
        </main>
      </div>
    </div>
  );
}
