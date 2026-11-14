import { ApiError } from './client';
import { TERMINAL_JOB_STATUSES, type Job } from './types';

export interface PollOptions {
  signal: AbortSignal;
  onUpdate?: (job: Job) => void;
  /** first delay, multiplier and ceiling in ms (default 1000 -> x1.5 -> 5000) */
  initialDelayMs?: number;
  factor?: number;
  maxDelayMs?: number;
  /** transient failures tolerated in a row before giving up */
  maxConsecutiveErrors?: number;
}

export const isTerminal = (job: Pick<Job, 'status'>): boolean => (TERMINAL_JOB_STATUSES as readonly string[]).includes(job.status);

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(new DOMException('Aborted', 'AbortError'));
    const t = setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(t);
      reject(new DOMException('Aborted', 'AbortError'));
    };
    signal.addEventListener('abort', onAbort, { once: true });
  });
}

/**
 * Poll a background job until it succeeds or fails. The delay grows (back-off) while nothing changes and
 * resets to the initial value whenever progress or status moves. Rejects with an AbortError when cancelled.
 */
export async function pollJob(fetchJob: (signal: AbortSignal) => Promise<Job>, opts: PollOptions): Promise<Job> {
  const { signal, onUpdate } = opts;
  const initial = opts.initialDelayMs ?? 1000;
  const factor = opts.factor ?? 1.5;
  const max = opts.maxDelayMs ?? 5000;
  const maxErrors = opts.maxConsecutiveErrors ?? 5;
  let delay = initial;
  let errors = 0;
  let last: { progress: number; status: string } | null = null;
  for (;;) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    try {
      const job = await fetchJob(signal);
      errors = 0;
      onUpdate?.(job);
      if (isTerminal(job)) return job;
      if (!last || last.progress !== job.progress || last.status !== job.status) delay = initial;
      else delay = Math.min(max, Math.round(delay * factor));
      last = { progress: job.progress, status: job.status };
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') throw e;
      if (e instanceof ApiError && [401, 403, 404].includes(e.status)) throw e;
      errors += 1;
      if (errors >= maxErrors) throw e;
      delay = Math.min(max, Math.round(delay * factor));
    }
    await sleep(delay, signal);
  }
}
