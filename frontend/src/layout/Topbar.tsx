import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { notificationApi } from '../api/endpoints';
import { useAuth } from '../auth/AuthContext';
import { Badge } from '../components/ui/basic';
import { Icon } from '../components/ui/Icon';
import { ProgressBar } from '../components/ui/feedback';
import { useApi } from '../hooks/useApi';
import { jobKindLabel } from '../lib/format';
import { safeInternalLink } from '../lib/links';
import { formatTs } from '../lib/time';
import { useJobs } from '../state/JobsContext';
import { useSociety } from '../state/SocietyContext';

/** A button that opens a popover panel; closes on Escape and outside click. */
function Popover({ label, icon, badge, children, align = 'right' }: { label: string; icon: ReactNode; badge?: ReactNode; children: ReactNode | ((close: () => void) => ReactNode); align?: 'left' | 'right' }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const panelId = useId();
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        ref.current?.querySelector('button')?.focus();
      }
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);
  return (
    <div className="relative" ref={ref}>
      <button type="button" className="btn-ghost relative !px-2" aria-label={label} aria-expanded={open} aria-controls={open ? panelId : undefined} aria-haspopup="true" onClick={() => setOpen((o) => !o)}>
        {icon}
        {badge}
      </button>
      {open && (
        <div id={panelId} className={`card absolute top-full z-30 mt-2 w-[min(22rem,calc(100vw-2rem))] p-3 shadow-xl ${align === 'right' ? 'right-0' : 'left-0'}`}>
          {typeof children === 'function' ? children(() => setOpen(false)) : children}
        </div>
      )}
    </div>
  );
}

function NotificationBell() {
  const { settledSeq } = useJobs();
  const nav = useNavigate();
  const [bump, setBump] = useState(0);
  const unread = useApi(`notifications-unread:${settledSeq}:${bump}`, (signal) => notificationApi.list({ unread_only: true, limit: 10 }, { signal }));
  const items = unread.data ?? [];
  const markAll = async () => {
    await notificationApi.readAll().catch(() => undefined);
    setBump((b) => b + 1);
  };
  return (
    <Popover
      label={items.length ? `Notifications, ${items.length} unread` : 'Notifications'}
      icon={<Icon name="bell" />}
      badge={
        items.length > 0 ? (
          <span className="num absolute -right-0.5 -top-0.5 min-w-[18px] rounded-full bg-accent px-1 text-center text-[11px] font-semibold leading-[18px] text-accent-ink">{items.length > 9 ? '9+' : items.length}</span>
        ) : null
      }
    >
      {(close) => (
        <div>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm">Unread notifications</h2>
            {items.length > 0 && (
              <button type="button" className="text-xs text-accent underline" onClick={markAll}>
                Mark all read
              </button>
            )}
          </div>
          {unread.error && <p className="text-xs text-bad">{unread.error.message}</p>}
          {!unread.error && items.length === 0 && <p className="py-3 text-sm text-ink-2">You are all caught up.</p>}
          <ul className="max-h-72 divide-y divide-line overflow-y-auto">
            {items.map((n) => {
              const href = safeInternalLink(n.link);
              return (
                <li key={n.id} className="py-2 text-sm">
                  <p className="text-ink">{n.message}</p>
                  <p className="num mt-0.5 flex items-center gap-3 text-xs text-muted">
                    {formatTs(n.created_at)}
                    {href && (
                      <button
                        type="button"
                        className="text-accent underline"
                        onClick={() => {
                          notificationApi.read(n.id).catch(() => undefined);
                          close();
                          nav(href);
                          setBump((b) => b + 1);
                        }}
                      >
                        Open
                      </button>
                    )}
                  </p>
                </li>
              );
            })}
          </ul>
          <Link to="/notifications" onClick={close} className="mt-2 block text-sm text-accent underline">
            All notifications
          </Link>
        </div>
      )}
    </Popover>
  );
}

function JobIndicator() {
  const { active } = useJobs();
  return (
    <Popover
      label={active.length ? `${active.length} job${active.length === 1 ? '' : 's'} running` : 'Background jobs'}
      icon={<Icon name="jobs" />}
      badge={active.length > 0 ? <span className="num absolute -right-0.5 -top-0.5 min-w-[18px] rounded-full bg-warn-soft px-1 text-center text-[11px] font-semibold leading-[18px] text-warn ring-1 ring-warn">{active.length}</span> : null}
    >
      {(close) => (
        <div>
          <h2 className="mb-2 text-sm">Running jobs</h2>
          {active.length === 0 && <p className="py-3 text-sm text-ink-2">No job is running.</p>}
          <ul className="space-y-3">
            {active.map((j) => (
              <li key={j.id}>
                <p className="mb-1 text-sm font-medium">{jobKindLabel(j.kind)}</p>
                <ProgressBar value={j.progress} label={`${jobKindLabel(j.kind)} progress`} message={j.message || j.status} />
              </li>
            ))}
          </ul>
          <Link to="/jobs" onClick={close} className="mt-3 block text-sm text-accent underline">
            All jobs
          </Link>
        </div>
      )}
    </Popover>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  if (!user) return null;
  return (
    <Popover label={`Account menu for ${user.email}`} icon={<Icon name="user" />}>
      {(close) => (
        <div className="text-sm">
          <p className="font-semibold">{user.full_name || user.email}</p>
          <p className="break-all text-xs text-ink-2">{user.email}</p>
          <p className="mt-2">
            <Badge tone={user.role === 'admin' ? 'accent' : 'neutral'}>{user.role}</Badge>
          </p>
          {user.role === 'viewer' && <p className="mt-2 text-xs text-ink-2">Viewer accounts are read-only: acknowledging alerts, creating reports and other changes are disabled.</p>}
          <button
            type="button"
            className="btn-secondary mt-3 w-full"
            onClick={() => {
              close();
              logout();
              nav('/login');
            }}
          >
            Sign out
          </button>
        </div>
      )}
    </Popover>
  );
}

const SOCIETY_PATHS = /^\/(consumption|forecasting|buildings|facilities|cost|alerts|recommendations|reports|data-sources|society-admin)?(\/|$)/;

/** Which society the page is about, and what kind of data it is, so the context stays visible while scrolling. */
function SocietyContextChip() {
  const { active } = useSociety();
  if (!active) return null;
  const upload = active.source_name === 'Administrator upload';
  const from = active.start.slice(0, 4);
  const to = active.end.slice(0, 4);
  return (
    <div className="flex min-w-0 items-center gap-2 text-sm" aria-label="Active society">
      <Icon name="building" className="h-[18px] w-[18px] shrink-0 text-accent" />
      <span className="truncate font-medium text-ink">{active.name}</span>
      <span className="hidden shrink-0 rounded-full border border-line-strong bg-sunken px-2 py-0.5 text-xs text-ink-2 md:inline">{upload ? 'Uploaded meter data' : `Historical data ${from === to ? from : `${from} to ${to}`}`}</span>
    </div>
  );
}

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const { pathname } = useLocation();
  return (
    <header className="sticky top-0 z-20 flex min-h-[58px] items-center gap-2 border-b border-line bg-surface/95 px-3 backdrop-blur sm:px-6 lg:px-9">
      <button type="button" className="btn-ghost !px-2 lg:hidden" onClick={onMenu} aria-label="Open navigation">
        <Icon name="menu" />
      </button>
      {SOCIETY_PATHS.test(pathname) ? <SocietyContextChip /> : null}
      <div className="ml-auto flex items-center gap-0.5">
        <JobIndicator />
        <NotificationBell />
        <UserMenu />
      </div>
    </header>
  );
}
