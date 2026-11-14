import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { tariffApi, societyApi } from '../api/endpoints';
import type { SocietySummary } from '../api/societyTypes';
import type { Tariff } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { useApi } from '../hooks/useApi';
import { KEYS, storageGet, storageRemove, storageSet } from '../lib/storage';
import { useJobs } from './JobsContext';

interface SocietyApi {
  societies: SocietySummary[];
  loading: boolean;
  error: Error | null;
  /** the society every society page works on; persisted in sessionStorage */
  active: SocietySummary | null;
  activeId: number | null;
  setActiveId: (id: number | null) => void;
  refresh: () => void;
  /** tariff used for every cost figure ("demo" is the built-in placeholder, never a real utility price) */
  tariffs: Tariff[];
  tariffId: number | string;
  tariff: Tariff | null;
  setTariffId: (id: number | string) => void;
  refreshTariffs: () => void;
}

const SocietyContext = createContext<SocietyApi | null>(null);

export function SocietyProvider({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const { settledSeq } = useJobs();
  const list = useApi<SocietySummary[]>(status === 'authenticated' ? `societies:${settledSeq}` : null, (signal) => societyApi.list({ signal }));
  const tariffList = useApi<Tariff[]>(status === 'authenticated' ? 'society-tariffs' : null, (signal) => tariffApi.list({ signal }));
  const [storedId, setStoredId] = useState<number | null>(() => {
    const v = storageGet('session', KEYS.activeSociety);
    return v && /^\d+$/.test(v) ? Number(v) : null;
  });
  const [storedTariff, setStoredTariff] = useState<string>(() => storageGet('session', KEYS.societyTariff) ?? 'demo');

  const societies = useMemo(() => list.data ?? [], [list.data]);
  // Selection falls back to the first society (alphabetical) when nothing valid is stored.
  const active = useMemo(() => {
    const picked = storedId !== null ? societies.find((s) => s.id === storedId) : undefined;
    return picked ?? societies.find((s) => s.key === 'fox') ?? societies[0] ?? null;
  }, [societies, storedId]);

  const setActiveId = useCallback((id: number | null) => {
    setStoredId(id);
    if (id === null) storageRemove('session', KEYS.activeSociety);
    else storageSet('session', KEYS.activeSociety, String(id));
  }, []);

  const tariffs = useMemo(() => tariffList.data ?? [], [tariffList.data]);
  const tariff = useMemo(() => tariffs.find((t) => String(t.id) === storedTariff) ?? tariffs.find((t) => t.id === 'demo') ?? null, [tariffs, storedTariff]);
  const tariffId: number | string = tariff?.id ?? 'demo';
  const setTariffId = useCallback((id: number | string) => {
    setStoredTariff(String(id));
    storageSet('session', KEYS.societyTariff, String(id));
  }, []);

  useEffect(() => {
    if (status === 'anonymous') {
      setStoredId(null);
      setStoredTariff('demo');
      storageRemove('session', KEYS.activeSociety);
      storageRemove('session', KEYS.societyTariff);
    }
  }, [status]);

  const { reload } = list;
  const { reload: reloadTariffs } = tariffList;
  const value = useMemo<SocietyApi>(
    () => ({
      societies, loading: list.loading && list.data === undefined, error: list.error, active, activeId: active?.id ?? null, setActiveId, refresh: reload,
      tariffs, tariffId, tariff, setTariffId, refreshTariffs: reloadTariffs,
    }),
    [societies, list.loading, list.data, list.error, active, setActiveId, reload, tariffs, tariffId, tariff, setTariffId, reloadTariffs],
  );
  return <SocietyContext.Provider value={value}>{children}</SocietyContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSociety(): SocietyApi {
  const ctx = useContext(SocietyContext);
  if (!ctx) throw new Error('useSociety must be used inside <SocietyProvider>');
  return ctx;
}
