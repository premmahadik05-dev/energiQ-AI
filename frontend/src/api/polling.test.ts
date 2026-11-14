import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Job } from './types';
import { ApiError } from './client';
import { isTerminal, pollJob } from './polling';
import { fx } from '../test/fixtures';

const job = (over: Partial<Job>): Job => ({ ...(fx.trainAccepted as unknown as Job), ...over });

describe('pollJob', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('resolves with the final job once it succeeds, polling about once a second', async () => {
    const seq = [job({ status: 'queued' }), job({ status: 'running', progress: 0.4 }), job({ status: 'succeeded', progress: 1 })];
    const fetchJob = vi.fn(async () => seq.shift() as Job);
    const seen: string[] = [];
    const p = pollJob(fetchJob, { signal: new AbortController().signal, onUpdate: (j) => seen.push(j.status) });
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchJob).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchJob).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1000);
    await expect(p).resolves.toMatchObject({ status: 'succeeded' });
    expect(seen).toEqual(['queued', 'running', 'succeeded']);
  });

  it('resolves (does not throw) for a failed job so the caller can show job.error', async () => {
    const fetchJob = vi.fn(async () => job({ status: 'failed', error: 'Missing expected column' }));
    await expect(pollJob(fetchJob, { signal: new AbortController().signal })).resolves.toMatchObject({ status: 'failed', error: 'Missing expected column' });
    expect(isTerminal({ status: 'failed' })).toBe(true);
    expect(isTerminal({ status: 'running' })).toBe(false);
  });

  it('backs off 1 s, 1.5 s, 2.25 s ... up to the ceiling while nothing changes, and resets when progress moves', async () => {
    const times: number[] = [];
    let n = 0;
    const fetchJob = vi.fn(async () => {
      times.push(Date.now());
      n += 1;
      if (n === 8) return job({ status: 'succeeded', progress: 1 });
      // progress changes only at the 5th poll
      return job({ status: 'running', progress: n >= 5 ? 0.5 : 0.1 });
    });
    const t0 = Date.now();
    const p = pollJob(fetchJob, { signal: new AbortController().signal, initialDelayMs: 1000, factor: 2, maxDelayMs: 4000 });
    await vi.advanceTimersByTimeAsync(60_000);
    await p;
    const gaps = times.map((t, i) => (i === 0 ? t - t0 : t - (times[i - 1] as number)));
    // polls 2..4: unchanged -> 1000 then 2000 then 4000 (capped); poll 5 sees new progress -> delay resets to 1000
    expect(gaps.slice(1)).toEqual([1000, 2000, 4000, 4000, 1000, 2000, 4000].slice(0, gaps.length - 1));
    expect(Math.max(...gaps)).toBeLessThanOrEqual(4000);
  });

  it('stops immediately when aborted and rejects with AbortError', async () => {
    const ctl = new AbortController();
    const fetchJob = vi.fn(async () => job({ status: 'running' }));
    const p = pollJob(fetchJob, { signal: ctl.signal });
    const assertion = expect(p).rejects.toMatchObject({ name: 'AbortError' });
    await vi.advanceTimersByTimeAsync(1500);
    const calls = fetchJob.mock.calls.length;
    ctl.abort();
    await assertion;
    await vi.advanceTimersByTimeAsync(20_000);
    expect(fetchJob.mock.calls.length).toBe(calls);
  });

  it('tolerates transient failures but gives up after the configured number in a row', async () => {
    const fetchJob = vi.fn(async () => {
      throw new ApiError(500, 'boom');
    });
    const p = pollJob(fetchJob, { signal: new AbortController().signal, maxConsecutiveErrors: 3 });
    const assertion = expect(p).rejects.toMatchObject({ status: 500 });
    await vi.advanceTimersByTimeAsync(30_000);
    await assertion;
    expect(fetchJob).toHaveBeenCalledTimes(3);
  });

  it('rethrows 404 at once (job does not exist or belongs to someone else)', async () => {
    const fetchJob = vi.fn(async () => {
      throw new ApiError(404, 'Not found');
    });
    await expect(pollJob(fetchJob, { signal: new AbortController().signal })).rejects.toMatchObject({ status: 404 });
    expect(fetchJob).toHaveBeenCalledTimes(1);
  });
});
