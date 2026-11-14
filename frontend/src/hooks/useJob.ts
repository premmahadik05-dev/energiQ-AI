import { useEffect, useRef, useState } from 'react';
import { isAbortError } from '../api/client';
import { jobApi } from '../api/endpoints';
import { pollJob, type PollOptions } from '../api/polling';
import type { Job } from '../api/types';

export interface UseJobOptions extends Partial<Pick<PollOptions, 'initialDelayMs' | 'factor' | 'maxDelayMs' | 'maxConsecutiveErrors'>> {
  onUpdate?: (job: Job) => void;
  onSettled?: (job: Job) => void;
  fetchJob?: (id: number, signal: AbortSignal) => Promise<Job>;
}

/** Poll one background job. Polling stops on a terminal status, when jobId changes, and on unmount. */
export function useJob(jobId: number | null, options: UseJobOptions = {}): { job: Job | null; error: Error | null } {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const optsRef = useRef(options);
  optsRef.current = options;

  useEffect(() => {
    if (jobId === null) return;
    const ctl = new AbortController();
    setJob(null);
    setError(null);
    const o = optsRef.current;
    const fetchJob = o.fetchJob ?? ((id: number, signal: AbortSignal) => jobApi.get(id, { signal }));
    pollJob((signal) => fetchJob(jobId, signal), {
      signal: ctl.signal,
      initialDelayMs: o.initialDelayMs,
      factor: o.factor,
      maxDelayMs: o.maxDelayMs,
      maxConsecutiveErrors: o.maxConsecutiveErrors,
      onUpdate: (j) => {
        if (ctl.signal.aborted) return;
        setJob(j);
        optsRef.current.onUpdate?.(j);
      },
    }).then(
      (j) => {
        if (!ctl.signal.aborted) optsRef.current.onSettled?.(j);
      },
      (e: unknown) => {
        if (ctl.signal.aborted || isAbortError(e)) return;
        setError(e instanceof Error ? e : new Error(String(e)));
      },
    );
    return () => ctl.abort();
  }, [jobId]);

  return { job, error };
}
