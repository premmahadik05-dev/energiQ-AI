import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, isAbortError } from '../api/client';

export interface ApiState<T> {
  data: T | undefined;
  error: Error | null;
  loading: boolean;
  reload: () => void;
}

/**
 * Fetch on mount and whenever `key` changes (null = disabled). The fetcher receives an AbortSignal that is
 * triggered when the key changes or the component unmounts, and stale responses are ignored.
 * Data for a previous key is never shown for a new key; a plain reload() keeps the old data on screen.
 */
export function useApi<T>(key: string | null, fetcher: (signal: AbortSignal) => Promise<T>): ApiState<T> {
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const [nonce, setNonce] = useState(0);
  const [state, setState] = useState<{ key: string | null; data?: T; error: Error | null; loading: boolean }>({ key, error: null, loading: key !== null });

  useEffect(() => {
    if (key === null) {
      setState({ key, error: null, loading: false });
      return;
    }
    const ctl = new AbortController();
    setState((s) => ({ key, data: s.key === key ? s.data : undefined, error: null, loading: true }));
    fetcherRef.current(ctl.signal).then(
      (data) => {
        if (!ctl.signal.aborted) setState({ key, data, error: null, loading: false });
      },
      (error: unknown) => {
        if (ctl.signal.aborted || isAbortError(error)) return;
        setState((s) => ({ key, data: s.key === key ? s.data : undefined, error: error instanceof Error ? error : new ApiError(0, String(error)), loading: false }));
      },
    );
    return () => ctl.abort();
  }, [key, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const current = state.key === key;
  return { data: current ? state.data : undefined, error: current ? state.error : null, loading: key === null ? false : current ? state.loading : true, reload };
}
