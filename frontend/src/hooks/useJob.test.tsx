import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Job } from '../api/types';
import { fx } from '../test/fixtures';
import { useJob } from './useJob';

const base = fx.trainAccepted as unknown as Job;
const job = (over: Partial<Job>): Job => ({ ...base, ...over });

describe('useJob', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('polls until the job succeeds, exposes progress and calls onSettled once', async () => {
    const seq = [job({ status: 'queued' }), job({ status: 'running', progress: 0.5 }), job({ status: 'succeeded', progress: 1, result: { model_id: 'm1' } })];
    const fetchJob = vi.fn(async () => seq.shift() as Job);
    const onSettled = vi.fn();
    const { result } = renderHook(() => useJob(7, { fetchJob, onSettled }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.job?.status).toBe('queued');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.job).toMatchObject({ status: 'running', progress: 0.5 });
    expect(onSettled).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.job?.status).toBe('succeeded');
    expect(onSettled).toHaveBeenCalledTimes(1);
    expect(fetchJob).toHaveBeenCalledWith(7, expect.any(AbortSignal));
    // terminal: no further polling
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(fetchJob).toHaveBeenCalledTimes(3);
  });

  it('settles with a failed job and keeps the server error text', async () => {
    const fetchJob = vi.fn(async () => job({ status: 'failed', error: 'Sampling interval is coarser than hourly' }));
    const onSettled = vi.fn();
    const { result } = renderHook(() => useJob(3, { fetchJob, onSettled }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.job?.error).toBe('Sampling interval is coarser than hourly');
    expect(onSettled).toHaveBeenCalledWith(expect.objectContaining({ status: 'failed' }));
  });

  it('cancels polling when the component unmounts', async () => {
    const fetchJob = vi.fn(async () => job({ status: 'running', progress: 0.1 }));
    const onSettled = vi.fn();
    const { unmount } = renderHook(() => useJob(9, { fetchJob, onSettled }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    const callsAtUnmount = fetchJob.mock.calls.length;
    expect(callsAtUnmount).toBeGreaterThanOrEqual(2);
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(fetchJob.mock.calls.length).toBe(callsAtUnmount);
    expect(onSettled).not.toHaveBeenCalled();
  });

  it('does not poll when there is no job id, and restarts for a new id', async () => {
    const fetchJob = vi.fn(async (id: number) => job({ id, status: 'succeeded', progress: 1 }));
    const { result, rerender } = renderHook(({ id }: { id: number | null }) => useJob(id, { fetchJob }), { initialProps: { id: null as number | null } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(fetchJob).not.toHaveBeenCalled();
    expect(result.current.job).toBeNull();
    rerender({ id: 11 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.job?.id).toBe(11);
  });

  it('reports an error when the job cannot be fetched (404)', async () => {
    const { ApiError } = await import('../api/client');
    const fetchJob = vi.fn(async () => {
      throw new ApiError(404, 'Not found');
    });
    const { result } = renderHook(() => useJob(5, { fetchJob }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.error?.message).toBe('Not found');
  });
});
