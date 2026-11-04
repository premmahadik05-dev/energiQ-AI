import { useEffect, useState } from 'react';
import { isAbortError } from '../api/client';
import type { BlobResult } from '../api/client';

/** Fetch an authenticated blob and expose it as an object URL that is revoked when it is replaced or the component unmounts. */
export function useBlobUrl(key: string | null, fetcher: () => Promise<BlobResult>): { url: string | null; error: Error | null; loading: boolean } {
  const [state, setState] = useState<{ key: string | null; url: string | null; error: Error | null }>({ key: null, url: null, error: null });

  useEffect(() => {
    if (key === null) return;
    let cancelled = false;
    let created: string | null = null;
    fetcher().then(
      (res) => {
        if (cancelled) return;
        created = URL.createObjectURL(res.blob);
        setState({ key, url: created, error: null });
      },
      (e: unknown) => {
        if (cancelled || isAbortError(e)) return;
        setState({ key, url: null, error: e instanceof Error ? e : new Error(String(e)) });
      },
    );
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the key identifies the resource; the fetcher closure is recreated every render
  }, [key]);

  const current = state.key === key;
  return { url: current ? state.url : null, error: current ? state.error : null, loading: key !== null && !current };
}
