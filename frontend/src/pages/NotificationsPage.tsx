import { useState } from 'react';
import { Link } from 'react-router-dom';
import { notificationApi } from '../api/endpoints';
import { Badge, Card, PageHeader } from '../components/ui/basic';
import { EmptyState, ErrorState, Loading } from '../components/ui/feedback';
import { Segmented } from '../components/ui/forms';
import { useApi } from '../hooks/useApi';
import { safeInternalLink } from '../lib/links';
import { formatTs } from '../lib/time';
import { useJobs } from '../state/JobsContext';
import { useToast } from '../state/ToastContext';

export function NotificationsPage() {
  const { settledSeq } = useJobs();
  const toast = useToast();
  const [filter, setFilter] = useState<'all' | 'unread'>('all');
  const [nonce, setNonce] = useState(0);
  const res = useApi(`notifications:${filter}:${settledSeq}:${nonce}`, (signal) => notificationApi.list({ unread_only: filter === 'unread', limit: 100 }, { signal }));
  const items = res.data ?? [];
  const unread = items.filter((n) => !n.is_read).length;

  const readOne = async (id: number) => {
    try {
      await notificationApi.read(id);
      setNonce((n) => n + 1);
    } catch (e) {
      toast.push(e instanceof Error ? e.message : 'Could not mark as read.', 'error');
    }
  };
  const readAll = async () => {
    try {
      await notificationApi.readAll();
      setNonce((n) => n + 1);
    } catch (e) {
      toast.push(e instanceof Error ? e.message : 'Could not mark all as read.', 'error');
    }
  };

  return (
    <>
      <PageHeader
        title="Notifications"
        description="Messages about finished training runs and detections."
        actions={
          <button type="button" className="btn-secondary" onClick={readAll} disabled={unread === 0}>
            Mark all as read
          </button>
        }
      />
      <Card>
        <div className="mb-4">
          <Segmented label="Show" hideLabel={false} value={filter} onChange={setFilter} options={[{ value: 'all', label: 'All' }, { value: 'unread', label: 'Unread' }]} />
        </div>
        {res.loading && !res.data && <Loading label="Loading notifications" />}
        {res.error && <ErrorState error={res.error} onRetry={res.reload} />}
        {res.data && items.length === 0 && <EmptyState title={filter === 'unread' ? 'Nothing unread' : 'No notifications yet'}>Notifications appear when a model finishes training or a detection run completes.</EmptyState>}
        <ul className="divide-y divide-line">
          {items.map((n) => {
            const href = safeInternalLink(n.link);
            return (
              <li key={n.id} className="flex flex-wrap items-start justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className={n.is_read ? 'text-ink-2' : 'font-medium'}>
                    {!n.is_read && <Badge tone="accent">new</Badge>} {n.message}
                  </p>
                  <p className="num mt-0.5 text-xs text-muted">{formatTs(n.created_at)} (server clock) · {n.kind}</p>
                </div>
                <div className="flex gap-2">
                  {href && (
                    <Link to={href} className="btn-secondary !min-h-[30px] !px-2 text-xs" onClick={() => !n.is_read && notificationApi.read(n.id).catch(() => undefined)}>
                      Open
                    </Link>
                  )}
                  {!n.is_read && (
                    <button type="button" className="btn-ghost !min-h-[30px] !px-2 text-xs" onClick={() => readOne(n.id)}>
                      Mark as read
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </Card>
    </>
  );
}
