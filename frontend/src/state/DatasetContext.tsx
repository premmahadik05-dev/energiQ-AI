import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { datasetApi } from '../api/endpoints';
import type { Dataset } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { useApi } from '../hooks/useApi';
import { KEYS, storageGet, storageRemove, storageSet } from '../lib/storage';
import { useJobs } from './JobsContext';

interface DatasetApi {
  datasets: Dataset[];
  loading: boolean;
  error: Error | null;
  /** the dataset every page works on; persisted in sessionStorage */
  active: Dataset | null;
  activeId: number | null;
  setActiveId: (id: number | null) => void;
  refresh: () => void;
}

const DatasetContext = createContext<DatasetApi | null>(null);

export function DatasetProvider({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const { settledSeq } = useJobs();
  const list = useApi<Dataset[]>(status === 'authenticated' ? `datasets:${settledSeq}` : null, (signal) => datasetApi.list({ signal }));
  const [storedId, setStoredId] = useState<number | null>(() => {
    const v = storageGet('session', KEYS.activeDataset);
    return v && /^\d+$/.test(v) ? Number(v) : null;
  });

  const datasets = useMemo(() => list.data ?? [], [list.data]);
  // Selection falls back to the newest ready dataset when nothing (valid) is stored.
  const active = useMemo(() => {
    const picked = storedId !== null ? datasets.find((d) => d.id === storedId) : undefined;
    return picked ?? datasets.find((d) => d.status === 'ready') ?? datasets[0] ?? null;
  }, [datasets, storedId]);

  const setActiveId = useCallback((id: number | null) => {
    setStoredId(id);
    if (id === null) storageRemove('session', KEYS.activeDataset);
    else storageSet('session', KEYS.activeDataset, String(id));
  }, []);

  useEffect(() => {
    if (status === 'anonymous') {
      setStoredId(null);
      storageRemove('session', KEYS.activeDataset);
    }
  }, [status]);

  const { reload } = list;
  const value = useMemo<DatasetApi>(
    () => ({ datasets, loading: list.loading && list.data === undefined, error: list.error, active, activeId: active?.id ?? null, setActiveId, refresh: reload }),
    [datasets, list.loading, list.data, list.error, active, setActiveId, reload],
  );
  return <DatasetContext.Provider value={value}>{children}</DatasetContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useDatasets(): DatasetApi {
  const ctx = useContext(DatasetContext);
  if (!ctx) throw new Error('useDatasets must be used inside <DatasetProvider>');
  return ctx;
}
