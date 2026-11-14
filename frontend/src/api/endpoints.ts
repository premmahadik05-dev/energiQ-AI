import { API_PREFIX, request, requestBlob, type BlobResult } from './client';
import type { AuditEvent, Job, Notification, RecommendationsResponse, SystemInfo, Tariff, TariffInput, TokenResponse, User, Role } from './types';
import type {
  AlertSeverity, Backtest, BuildingsMonthly, CommunityComparison, ErrorAnalysis, BuildingsResponse, ConsumptionPoint, ConsumptionResponse, FacilitiesResponse, ModelsResponse, PeaksResponse, ReportKind, Resolution,
  SocietyAnomaly, SocietyAnomalyList, SocietyCost, SocietyDetail, SocietyForecast, SocietyGlobalExplanation, SocietyLocalExplanation, SocietyOverview, SocietyReport, SocietySummary,
} from './societyTypes';

const v1 = (p: string) => `${API_PREFIX}${p}`;
type Sig = { signal?: AbortSignal };

export const authApi = {
  login: (email: string, password: string) => request<TokenResponse>(v1('/auth/login'), { method: 'POST', body: { email, password }, auth: false }),
  register: (email: string, password: string, full_name: string) =>
    request<User>(v1('/auth/register'), { method: 'POST', body: { email, password, full_name }, auth: false }),
  me: (o: Sig = {}) => request<User>(v1('/auth/me'), o),
};

export const jobApi = {
  get: (id: number, o: Sig = {}) => request<Job>(v1(`/jobs/${id}`), o),
  list: (q: { limit?: number } = {}, o: Sig = {}) => request<Job[]>(v1('/jobs'), { query: q, ...o }),
};

export const tariffApi = {
  list: (o: Sig = {}) => request<Tariff[]>(v1('/tariffs'), o),
  create: (body: TariffInput) => request<Tariff>(v1('/tariffs'), { method: 'POST', body }),
  remove: (id: number | string) => request<void>(v1(`/tariffs/${id}`), { method: 'DELETE' }),
};

export const notificationApi = {
  list: (q: { unread_only?: boolean; limit?: number } = {}, o: Sig = {}) => request<Notification[]>(v1('/notifications'), { query: q, ...o }),
  read: (id: number) => request<Notification>(v1(`/notifications/${id}/read`), { method: 'POST' }),
  readAll: () => request<void>(v1('/notifications/read-all'), { method: 'POST' }),
};

export const adminApi = {
  users: (o: Sig = {}) => request<User[]>(v1('/admin/users'), o),
  patchUser: (id: number, body: { role?: Role; is_active?: boolean }) => request<User>(v1(`/admin/users/${id}`), { method: 'PATCH', body }),
  audit: (q: { limit?: number; action?: string }, o: Sig = {}) => request<AuditEvent[]>(v1('/admin/audit'), { query: q, ...o }),
  system: (o: Sig = {}) => request<SystemInfo>(v1('/admin/system'), o),
};

// ----------------------------------------------------------------------------- society level
export interface RangeQuery {
  start?: string;
  end?: string;
}

export interface SocietyAnomalyQuery extends RangeQuery {
  scope?: 'society' | 'building';
  severity?: AlertSeverity;
  min_severity?: number;
  building_id?: number;
  acknowledged?: boolean;
  sort?: 'time' | 'severity';
  limit?: number;
  offset?: number;
}

const soc = (id: number, p = '') => v1(`/societies/${id}${p}`);

export const societyApi = {
  list: (o: Sig = {}) => request<SocietySummary[]>(v1('/societies'), o),
  detail: (id: number, o: Sig = {}) => request<SocietyDetail>(soc(id), o),
  remove: (id: number) => request<void>(soc(id), { method: 'DELETE' }),
  overview: (id: number, tariffId: number | string, o: Sig = {}) => request<SocietyOverview>(soc(id, '/overview'), { query: { tariff_id: tariffId }, ...o }),
  consumption: (id: number, q: RangeQuery & { resolution: Resolution }, o: Sig = {}) => request<ConsumptionResponse>(soc(id, '/consumption'), { query: { ...q }, ...o }),
  buildings: (id: number, q: RangeQuery, o: Sig = {}) => request<BuildingsResponse>(soc(id, '/buildings'), { query: { ...q }, ...o }),
  buildingConsumption: (id: number, bid: number, q: RangeQuery & { resolution: Resolution }, o: Sig = {}) =>
    request<{ building: string; points: ConsumptionPoint[] }>(soc(id, `/buildings/${bid}/consumption`), { query: { ...q }, ...o }),
  buildingsMonthly: (id: number, o: Sig = {}) => request<BuildingsMonthly>(soc(id, '/buildings-monthly'), o),
  patchBuilding: (id: number, bid: number, is_active: boolean) => request<{ id: number; code: string; is_active: boolean }>(soc(id, `/buildings/${bid}`), { method: 'PATCH', body: { is_active } }),
  facilities: (id: number, q: RangeQuery & { resolution?: string }, o: Sig = {}) => request<FacilitiesResponse>(soc(id, '/facilities'), { query: { ...q }, ...o }),
  peaks: (id: number, q: RangeQuery, o: Sig = {}) => request<PeaksResponse>(soc(id, '/peaks'), { query: { ...q }, ...o }),
  errorAnalysis: (id: number, horizon: number, o: Sig = {}) => request<ErrorAnalysis>(soc(id, '/error-analysis'), { query: { horizon }, ...o }),
  compare: (o: Sig = {}) => request<CommunityComparison>(v1('/societies/compare'), o),
  models: (id: number, o: Sig = {}) => request<ModelsResponse>(soc(id, '/models'), o),
  forecast: (id: number, q: { origin?: string; horizons?: string; tariff_id?: number | string }, o: Sig = {}) => request<SocietyForecast>(soc(id, '/forecast'), { query: { ...q }, ...o }),
  backtest: (id: number, q: RangeQuery & { horizon: number; limit?: number }, o: Sig = {}) => request<Backtest>(soc(id, '/backtest'), { query: { ...q }, ...o }),
  explainGlobal: (id: number, o: Sig = {}) => request<SocietyGlobalExplanation>(soc(id, '/explain/global'), o),
  explainLocal: (id: number, body: { horizon: number; origin?: string }, o: Sig = {}) => request<SocietyLocalExplanation>(soc(id, '/explain/local'), { method: 'POST', body, ...o }),
  anomalies: (id: number, q: SocietyAnomalyQuery, o: Sig = {}) => request<SocietyAnomalyList>(soc(id, '/anomalies'), { query: { ...q }, ...o }),
  acknowledge: (id: number, eid: number, acknowledged: boolean) => request<SocietyAnomaly>(soc(id, `/anomalies/${eid}`), { method: 'PATCH', body: { acknowledged } }),
  cost: (id: number, body: { tariff_id: number | string; start?: string; end?: string }, o: Sig = {}) => request<SocietyCost>(soc(id, '/cost'), { method: 'POST', body, ...o }),
  recommendations: (id: number, tariffId: number | string, o: Sig = {}) => request<RecommendationsResponse>(soc(id, '/recommendations'), { method: 'POST', body: { tariff_id: tariffId }, ...o }),
  reports: (id: number, o: Sig = {}) => request<SocietyReport[]>(soc(id, '/reports'), o),
  createReport: (id: number, body: { kind: ReportKind; format: 'pdf' | 'csv'; start?: string; end?: string; resolution?: Resolution; horizon?: number; tariff_id?: number | string }) =>
    request<SocietyReport>(soc(id, '/reports'), { method: 'POST', body }),
  downloadReport: (id: number, rid: number): Promise<BlobResult> => requestBlob(soc(id, `/reports/${rid}/download`)),
  importBundled: () => request<Job>(v1('/admin/societies/import-bundled'), { method: 'POST' }),
  train: (id: number) => request<Job>(v1(`/admin/societies/${id}/train`), { method: 'POST' }),
  meters: (id: number, o: Sig = {}) => request<SocietyMeter[]>(soc(id, '/meters'), o),
  upload: (f: { name: string; unit: 'kwh' | 'kw'; description: string; file: File; mapping: File | null }) => {
    const form = new FormData();
    form.append('file', f.file);
    if (f.mapping) form.append('mapping', f.mapping);
    form.append('name', f.name);
    form.append('unit', f.unit);
    form.append('description', f.description);
    return request<Job>(v1('/admin/societies/upload'), { method: 'POST', form });
  },
};

export interface SocietyMeter {
  id: number;
  code: string;
  building: string | null;
  building_id: number | null;
  kind: 'building' | 'facility';
  facility_category: string | null;
  meter_type: string;
  unit: string;
  interval_minutes: number;
  valid_share: number | null;
  is_active: boolean;
}
