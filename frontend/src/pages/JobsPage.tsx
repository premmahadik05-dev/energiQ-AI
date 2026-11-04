import { jobApi } from '../api/endpoints';
import type { Job } from '../api/types';
import { Card, PageHeader, StatusBadge } from '../components/ui/basic';
import { ErrorState, Loading, ProgressBar } from '../components/ui/feedback';
import { Table, type Column } from '../components/ui/Table';
import { useApi } from '../hooks/useApi';
import { evidenceLabel, evidenceValue } from '../lib/evidence';
import { jobKindLabel } from '../lib/format';
import { formatTs } from '../lib/time';
import { useJobs } from '../state/JobsContext';

function resultText(j: Job): string {
  if (j.error) return j.error;
  if (!j.result) return '–';
  return Object.entries(j.result)
    .filter(([, v]) => typeof v !== 'object' || v === null)
    .map(([k, v]) => `${evidenceLabel(k)}: ${evidenceValue(v)}`)
    .join(' · ') || '–';
}

export function JobsPage() {
  const { settledSeq, active } = useJobs();
  const res = useApi(`jobs:${settledSeq}:${active.length}`, (signal) => jobApi.list({ limit: 50 }, { signal }));
  const columns: Column<Job>[] = [
    { key: 'id', header: 'Job', render: (j) => `#${j.id}` },
    { key: 'k', header: 'Kind', render: (j) => jobKindLabel(j.kind) },
    { key: 's', header: 'Status', render: (j) => <StatusBadge status={j.status} /> },
    { key: 'p', header: 'Progress', className: 'min-w-[10rem]', render: (j) => <ProgressBar value={j.progress} label={`Job ${j.id} progress`} message={j.status === 'running' ? j.message : undefined} /> },
    { key: 'd', header: 'Dataset', align: 'right', render: (j) => j.dataset_id ?? '–' },
    { key: 'c', header: 'Created (server clock)', render: (j) => formatTs(j.created_at) },
    { key: 'f', header: 'Finished', render: (j) => formatTs(j.finished_at) },
    { key: 'r', header: 'Result or error', className: 'max-w-sm', render: (j) => <span className={j.error ? 'text-bad' : 'text-xs text-ink-2'}>{resultText(j)}</span> },
  ];
  return (
    <>
      <PageHeader title="Jobs" description="Uploads, training runs and detections run in the background. The 50 most recent are listed." />
      <Card padded={false}>
        <div className="p-4 sm:p-5">
          {res.loading && !res.data && <Loading label="Loading jobs" />}
          {res.error && <ErrorState error={res.error} onRetry={res.reload} />}
          {res.data && <Table columns={columns} rows={res.data} rowKey={(j) => j.id} caption="Background jobs" empty="No jobs yet." />}
        </div>
      </Card>
    </>
  );
}
