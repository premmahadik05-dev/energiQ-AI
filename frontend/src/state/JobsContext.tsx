import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { jobApi } from '../api/endpoints';
import { isTerminal } from '../api/polling';
import type { Job } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { useJob } from '../hooks/useJob';
import { jobKindLabel } from '../lib/format';
import { useToast } from './ToastContext';

interface JobsApi {
  /** jobs started or resumed in this session, newest first */
  jobs: Job[];
  active: Job[];
  /** start following a job returned by a POST (202) */
  track: (job: Job) => void;
  /** increments every time a tracked job reaches a terminal state; use it as part of a data key to refresh after jobs */
  settledSeq: number;
  lastSettled: Job | null;
}

const JobsContext = createContext<JobsApi | null>(null);


function JobWatcher({ jobId, onUpdate, onSettled }: { jobId: number; onUpdate: (j: Job) => void; onSettled: (j: Job) => void }) {
  useJob(jobId, { onUpdate, onSettled });
  return null;
}

export function JobsProvider({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const toast = useToast();
  const [byId, setById] = useState<Record<number, Job>>({});
  const [settledSeq, setSettledSeq] = useState(0);
  const [lastSettled, setLastSettled] = useState<Job | null>(null);

  const upsert = useCallback((j: Job) => setById((m) => ({ ...m, [j.id]: j })), []);
  const track = upsert;

  // Resume jobs that were still running when the page was loaded (reload, second tab).
  useEffect(() => {
    if (status !== 'authenticated') {
      setById({});
      return;
    }
    const ctl = new AbortController();
    jobApi.list({ limit: 20 }, { signal: ctl.signal }).then(
      (list) => setById((m) => ({ ...Object.fromEntries(list.filter((j) => !isTerminal(j)).map((j) => [j.id, j])), ...m })),
      () => undefined,
    );
    return () => ctl.abort();
  }, [status]);

  const onSettled = useCallback(
    (j: Job) => {
      upsert(j);
      setLastSettled(j);
      setSettledSeq((n) => n + 1);
      const label = jobKindLabel(j.kind);
      if (j.status === 'succeeded') toast.push(`${label} finished.`, 'success');
      else toast.push(`${label} failed: ${j.error ?? 'unknown error'}`, 'error');
    },
    [toast, upsert],
  );

  const jobs = useMemo(() => Object.values(byId).sort((a, b) => b.id - a.id), [byId]);
  const active = useMemo(() => jobs.filter((j) => !isTerminal(j)), [jobs]);
  const api = useMemo<JobsApi>(() => ({ jobs, active, track, settledSeq, lastSettled }), [jobs, active, track, settledSeq, lastSettled]);

  return (
    <JobsContext.Provider value={api}>
      {children}
      {active.map((j) => (
        <JobWatcher key={j.id} jobId={j.id} onUpdate={upsert} onSettled={onSettled} />
      ))}
    </JobsContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useJobs(): JobsApi {
  const ctx = useContext(JobsContext);
  if (!ctx) throw new Error('useJobs must be used inside <JobsProvider>');
  return ctx;
}
