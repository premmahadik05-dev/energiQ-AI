import { useMemo, useState } from 'react';
import { adminApi } from '../api/endpoints';
import type { Role, User } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { Badge, Card, DescriptionList, PageHeader } from '../components/ui/basic';
import { ErrorState, Loading } from '../components/ui/feedback';
import { SelectField } from '../components/ui/forms';
import { Table, type Column } from '../components/ui/Table';
import { Tabs } from '../components/ui/Tabs';
import { useApi } from '../hooks/useApi';
import { fmtInt, fmtNum, fmtSeconds, humanize } from '../lib/format';
import { formatTs } from '../lib/time';
import { useToast } from '../state/ToastContext';

function UsersTab() {
  const { user: me } = useAuth();
  const toast = useToast();
  const users = useApi<User[]>('admin-users', (signal) => adminApi.users({ signal }));
  const [busy, setBusy] = useState<number | null>(null);

  const patch = async (u: User, body: { role?: Role; is_active?: boolean }) => {
    setBusy(u.id);
    try {
      await adminApi.patchUser(u.id, body);
      toast.push(`Updated ${u.email}.`, 'success');
      users.reload();
    } catch (e) {
      toast.push(e instanceof Error ? e.message : 'Update failed.', 'error');
    } finally {
      setBusy(null);
    }
  };

  const columns: Column<User>[] = [
    { key: 'e', header: 'E-mail', render: (u) => <span>{u.email}{u.id === me?.id && <> <Badge tone="accent">you</Badge></>}<span className="block text-xs text-muted">{u.full_name}</span></span> },
    {
      key: 'r',
      header: 'Role',
      render: (u) => (
        <select aria-label={`Role for ${u.email}`} className="input !min-h-[32px] w-32 py-1" value={u.role} disabled={u.id === me?.id || busy === u.id} onChange={(e) => patch(u, { role: e.target.value as Role })}>
          <option value="admin">admin</option>
          <option value="analyst">analyst</option>
          <option value="viewer">viewer</option>
        </select>
      ),
    },
    { key: 's', header: 'Status', render: (u) => (u.is_active ? <Badge tone="good">✓ active</Badge> : <Badge tone="bad">deactivated</Badge>) },
    { key: 'c', header: 'Created', render: (u) => formatTs(u.created_at) },
    { key: 'l', header: 'Last sign-in', render: (u) => formatTs(u.last_login_at) },
    {
      key: 'a',
      header: 'Action',
      render: (u) =>
        u.id === me?.id ? (
          <span className="text-xs text-muted">You cannot change your own account</span>
        ) : (
          <button type="button" className="btn-secondary !min-h-[30px] !px-2 text-xs" disabled={busy === u.id} onClick={() => patch(u, { is_active: !u.is_active })}>
            {u.is_active ? 'Deactivate' : 'Reactivate'}
          </button>
        ),
    },
  ];
  if (users.loading && !users.data) return <Loading label="Loading users" />;
  if (users.error) return <ErrorState error={users.error} onRetry={users.reload} />;
  return <Table columns={columns} rows={users.data ?? []} rowKey={(u) => u.id} caption="User accounts" />;
}

function AuditTab() {
  const [action, setAction] = useState('');
  const [limit, setLimit] = useState('100');
  const known = useApi('admin-audit-all', (signal) => adminApi.audit({ limit: 500 }, { signal }));
  const log = useApi(`admin-audit:${action}:${limit}`, (signal) => adminApi.audit({ limit: Number(limit), action: action || undefined }, { signal }));
  const actions = useMemo(() => Array.from(new Set((known.data ?? []).map((e) => e.action))).sort(), [known.data]);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-4">
        <SelectField label="Action" value={action} onChange={(e) => setAction(e.target.value)} className="w-56" hint="Actions seen in the latest 500 events.">
          <option value="">All actions</option>
          {actions.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </SelectField>
        <SelectField label="Show" value={limit} onChange={(e) => setLimit(e.target.value)} className="w-40">
          {[50, 100, 200, 500].map((n) => (
            <option key={n} value={n}>
              Latest {n}
            </option>
          ))}
        </SelectField>
      </div>
      {log.loading && !log.data && <Loading label="Loading audit log" />}
      {log.error && <ErrorState error={log.error} onRetry={log.reload} />}
      {log.data && (
        <Table
          caption="Audit log"
          rows={log.data}
          rowKey={(e) => e.id}
          empty="No audit events match."
          columns={[
            { key: 'ts', header: 'Time (server clock)', render: (e) => formatTs(e.ts) },
            { key: 'a', header: 'Action', render: (e) => e.action },
            { key: 'u', header: 'User id', align: 'right', render: (e) => (e.user_id ?? '–') },
            { key: 'r', header: 'Resource', render: (e) => (e.resource_type ? `${e.resource_type} ${e.resource_id}` : '–') },
            { key: 'ip', header: 'IP', render: (e) => e.ip || '–' },
            { key: 'd', header: 'Detail', render: (e) => (Object.keys(e.detail).length ? <code className="break-all text-xs">{JSON.stringify(e.detail)}</code> : '–') },
          ]}
          dense
        />
      )}
    </div>
  );
}

function SystemTab() {
  const sys = useApi('admin-system', (signal) => adminApi.system({ signal }));
  if (sys.loading && !sys.data) return <Loading label="Loading system stats" />;
  if (sys.error) return <ErrorState error={sys.error} onRetry={sys.reload} />;
  const s = sys.data;
  if (!s) return null;
  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <button type="button" className="btn-secondary" onClick={sys.reload}>
          Refresh
        </button>
      </div>
      <Card title="Records">
        <DescriptionList columns={3} items={Object.entries(s.counts).map(([k, v]) => ({ label: humanize(k), value: fmtInt(v) }))} />
      </Card>
      <Card title="Jobs by status">
        {Object.keys(s.jobs_by_status).length === 0 ? <p className="text-sm text-ink-2">No jobs yet.</p> : <DescriptionList columns={3} items={Object.entries(s.jobs_by_status).map(([k, v]) => ({ label: humanize(k), value: fmtInt(v) }))} />}
      </Card>
      <Card title="API traffic since the server started" description={`Environment: ${s.environment}. Counters live in the server process and reset when it restarts.`}>
        <DescriptionList
          columns={3}
          items={[
            { label: 'Uptime', value: fmtSeconds(s.http.uptime_seconds) },
            { label: 'Requests', value: fmtInt(s.http.requests_total) },
            { label: 'Client errors (4xx)', value: fmtInt(s.http.responses_4xx) },
            { label: 'Server errors (5xx)', value: fmtInt(s.http.responses_5xx) },
            { label: 'Latency p50', value: s.http.latency_seconds.p50 != null ? `${fmtNum(s.http.latency_seconds.p50 * 1000, 0)} ms` : '–' },
            { label: 'Latency p95', value: s.http.latency_seconds.p95 != null ? `${fmtNum(s.http.latency_seconds.p95 * 1000, 0)} ms` : '–' },
            { label: 'Latency max', value: s.http.latency_seconds.max != null ? `${fmtNum(s.http.latency_seconds.max * 1000, 0)} ms` : '–' },
            { label: 'Requests in latency window', value: fmtInt(s.http.latency_seconds.window) },
          ]}
        />
      </Card>
    </div>
  );
}

export function AdminPage() {
  const [tab, setTab] = useState<'users' | 'audit' | 'system'>('users');
  return (
    <>
      <PageHeader title="Administration" description="Accounts, the audit trail and server health. Visible to administrators only." />
      <Tabs
        tabs={[{ id: 'users', label: 'Users' }, { id: 'audit', label: 'Audit log' }, { id: 'system', label: 'System' }]}
        value={tab}
        onChange={setTab}
        label="Administration sections"
      >
        {tab === 'users' && <UsersTab />}
        {tab === 'audit' && <AuditTab />}
        {tab === 'system' && <SystemTab />}
      </Tabs>
    </>
  );
}
