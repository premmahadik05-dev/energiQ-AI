import { API_PREFIX, request, requestBlob, type BlobResult } from './client';
import type {
  AnomalyEvent, AnomalyList, AnomalySummary, AuditEvent, Benchmark, CostResponse, Dataset, DatasetDetail, DatasetProfile, Forecast,
  GlobalExplanation, Job, LocalExplanation, ModelVersion, Monitoring, Notification, ReadingsResponse, DailyReadingPoint, ReadingPoint,
  RecommendationsResponse, ScheduleResponse, Severity, SystemInfo, Tariff, TokenResponse, UploadAccepted, User, Role,
} from './types';

const v1 = (p: string) => `${API_PREFIX}${p}`;
type Sig = { signal?: AbortSignal };

export const authApi = {
  login: (email: string, password: string) => request<TokenResponse>(v1('/auth/login'), { method: 'POST', body: { email, password }, auth: false }),
  register: (email: string, password: string, full_name: string) =>
    request<User>(v1('/auth/register'), { method: 'POST', body: { email, password, full_name }, auth: false }),
  me: (o: Sig = {}) => request<User>(v1('/auth/me'), o),
};

export interface UploadFields {
  name: string;
  value_column: string;
  unit: string;
  timestamp_column?: string;
  date_column?: string;
  time_column?: string;
  delimiter?: string;
  dayfirst: boolean;
  timestamp_format?: string;
  timezone_convention: string;
}

export const datasetApi = {
  list: (o: Sig = {}) => request<Dataset[]>(v1('/datasets'), o),
  detail: (id: number, o: Sig = {}) => request<DatasetDetail>(v1(`/datasets/${id}`), o),
  upload: (file: File, f: UploadFields) => {
    const form = new FormData();
    form.append('file', file);
    form.append('name', f.name);
    form.append('value_column', f.value_column);
    form.append('unit', f.unit);
    form.append('dayfirst', String(f.dayfirst));
    form.append('timezone_convention', f.timezone_convention);
    for (const k of ['timestamp_column', 'date_column', 'time_column', 'delimiter', 'timestamp_format'] as const) {
      const v = f[k];
      if (v && v.trim() !== '') form.append(k, v);
    }
    return request<UploadAccepted>(v1('/datasets'), { method: 'POST', form });
  },
  loadSample: () => request<UploadAccepted>(v1('/datasets/sample'), { method: 'POST' }),
  append: (id: number, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<UploadAccepted>(v1(`/datasets/${id}/append`), { method: 'POST', form });
  },
  remove: (id: number) => request<void>(v1(`/datasets/${id}`), { method: 'DELETE' }),
  readingsHourly: (id: number, q: { start?: string; end?: string; limit?: number }, o: Sig = {}) =>
    request<ReadingsResponse<ReadingPoint>>(v1(`/datasets/${id}/readings`), { query: { ...q, resolution: 'hourly' }, ...o }),
  readingsDaily: (id: number, q: { start?: string; end?: string; limit?: number }, o: Sig = {}) =>
    request<ReadingsResponse<DailyReadingPoint>>(v1(`/datasets/${id}/readings`), { query: { ...q, resolution: 'daily' }, ...o }),
  profile: (id: number, o: Sig = {}) => request<DatasetProfile>(v1(`/datasets/${id}/profile`), o),
  report: (id: number): Promise<BlobResult> => requestBlob(v1(`/datasets/${id}/report`)),
};

export const jobApi = {
  get: (id: number, o: Sig = {}) => request<Job>(v1(`/jobs/${id}`), o),
  list: (q: { limit?: number; dataset_id?: number } = {}, o: Sig = {}) => request<Job[]>(v1('/jobs'), { query: q, ...o }),
};

export const modelApi = {
  list: (datasetId?: number, o: Sig = {}) => request<ModelVersion[]>(v1('/models'), { query: { dataset_id: datasetId }, ...o }),
  get: (id: string, o: Sig = {}) => request<ModelVersion>(v1(`/models/${encodeURIComponent(id)}`), o),
  train: (datasetId: number, activate = true) => request<Job>(v1(`/datasets/${datasetId}/train`), { method: 'POST', body: { activate } }),
  activate: (id: string) => request<ModelVersion>(v1(`/models/${encodeURIComponent(id)}/activate`), { method: 'POST' }),
  remove: (id: string) => request<void>(v1(`/models/${encodeURIComponent(id)}`), { method: 'DELETE' }),
  monitoring: (id: string, recentDays: number, o: Sig = {}) =>
    request<Monitoring>(v1(`/models/${encodeURIComponent(id)}/monitoring`), { query: { recent_days: recentDays }, ...o }),
};

export const forecastApi = {
  create: (body: { dataset_id: number; model_id?: string; origin?: string }) => request<Forecast>(v1('/forecasts'), { method: 'POST', body }),
  list: (q: { dataset_id?: number; limit?: number }, o: Sig = {}) => request<Forecast[]>(v1('/forecasts'), { query: q, ...o }),
  get: (id: number, o: Sig = {}) => request<Forecast>(v1(`/forecasts/${id}`), o),
  exportCsv: (id: number): Promise<BlobResult> => requestBlob(v1(`/forecasts/${id}/export.csv`)),
};

export const explainApi = {
  global: (modelId: string, o: Sig = {}) => request<GlobalExplanation>(v1('/explain/global'), { query: { model_id: modelId }, ...o }),
  local: (body: { model_id: string; horizon: number; origin?: string }, o: Sig = {}) =>
    request<LocalExplanation>(v1('/explain/local'), { method: 'POST', body, ...o }),
};

export const anomalyApi = {
  run: (datasetId: number, sensitivity: 'low' | 'medium' | 'high') =>
    request<Job>(v1(`/datasets/${datasetId}/anomalies/run`), { method: 'POST', body: { sensitivity } }),
  list: (q: { dataset_id: number; severity?: Severity; acknowledged?: boolean; sort?: 'severity' | 'time'; limit?: number; offset?: number }, o: Sig = {}) =>
    request<AnomalyList>(v1('/anomalies'), { query: q, ...o }),
  summary: (datasetId: number, o: Sig = {}) => request<AnomalySummary>(v1('/anomalies/summary'), { query: { dataset_id: datasetId }, ...o }),
  acknowledge: (id: number, acknowledged: boolean) => request<AnomalyEvent>(v1(`/anomalies/${id}`), { method: 'PATCH', body: { acknowledged } }),
};

export interface TariffBody {
  name: string;
  currency: string;
  weekday_rates: number[];
  weekend_rates: number[];
  daily_fixed_charge: number;
}

export const optimizeApi = {
  tariffs: (o: Sig = {}) => request<Tariff[]>(v1('/tariffs'), o),
  createTariff: (body: TariffBody) => request<Tariff>(v1('/tariffs'), { method: 'POST', body }),
  deleteTariff: (id: number) => request<void>(v1(`/tariffs/${id}`), { method: 'DELETE' }),
  cost: (body: { dataset_id: number; tariff_id: number | string; start?: string; end?: string }, o: Sig = {}) =>
    request<CostResponse>(v1('/optimize/cost'), { method: 'POST', body, ...o }),
  recommendations: (body: { dataset_id: number; tariff_id: number | string; model_id?: string }) =>
    request<RecommendationsResponse>(v1('/optimize/recommendations'), { method: 'POST', body }),
  schedule: (body: { dataset_id?: number; tariff_id: number | string; duration_h: number; power_kw: number; start_after?: string }, o: Sig = {}) =>
    request<ScheduleResponse>(v1('/optimize/schedule'), { method: 'POST', body, ...o }),
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

export const benchmarkApi = {
  get: (o: Sig = {}) => request<Benchmark>(v1('/benchmark'), o),
  figure: (group: string, name: string, o: Sig = {}): Promise<BlobResult> =>
    requestBlob(v1(`/benchmark/figures/${encodeURIComponent(group)}/${encodeURIComponent(name)}`), o),
};
