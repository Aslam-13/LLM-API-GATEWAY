import axios from "axios";
import { clearToken, getToken } from "./auth";

const baseURL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

export const api = axios.create({ baseURL });

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers = config.headers ?? {};
    (config.headers as Record<string, string>).Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401 || err?.response?.status === 403) {
      clearToken();
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

// ---------- types ----------
export type ApiKeyRow = {
  id: string;
  name: string;
  prefix: string;
  email: string | null;
  admin: boolean;
  rate_limit_overrides: Record<string, number> | null;
  created_at: string;
  revoked_at: string | null;
  last_used_at: string | null;
};

export type CreatedKey = ApiKeyRow & { plaintext: string };

export type Overview = {
  totals_24h: {
    requests: number;
    cost_usd: number;
    tokens: number;
    cache_hit_rate: number;
    p95_latency_ms: number;
  };
  cache_breakdown_24h: { none: number; exact: number; semantic: number };
  requests_per_minute_1h: { minute: string; count: number }[];
  cache_hourly_24h: { hour: string; none: number; exact: number; semantic: number }[];
};

export type UsageRow = {
  id: number;
  request_id: string;
  api_key_id: string;
  model: string;
  provider: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  latency_ms: number;
  cache_hit: "none" | "exact" | "semantic";
  status: string;
  error: string | null;
  created_at: string;
};

export type UsageResponse = {
  total: number;
  aggregate: { requests: number; tokens: number; cost_usd: number; avg_latency_ms: number };
  daily: { day: string; requests: number; tokens: number; cost: number }[];
  rows: UsageRow[];
};

export type JobRow = {
  id: string;
  api_key_id: string;
  kind: string;
  status: "pending" | "running" | "succeeded" | "failed";
  input: Record<string, unknown>;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

// ---------- endpoints ----------
export const adminApi = {
  me: () => api.get("/admin/me").then((r) => r.data),
  overview: () => api.get<Overview>("/admin/stats/overview").then((r) => r.data),
  listKeys: () => api.get<ApiKeyRow[]>("/admin/keys").then((r) => r.data),
  createKey: (body: { name: string; email?: string; admin?: boolean }) =>
    api.post<CreatedKey>("/admin/keys", body).then((r) => r.data),
  revokeKey: (id: string) => api.delete(`/admin/keys/${id}`).then((r) => r.data),
  usage: (params: {
    api_key_id?: string;
    from?: string;
    to?: string;
    limit?: number;
    offset?: number;
  }) =>
    api
      .get<UsageResponse>("/admin/usage", { params: { ...params, from: params.from } })
      .then((r) => r.data),
  jobs: (params: { status?: string; limit?: number; offset?: number } = {}) =>
    api
      .get<{ total: number; rows: JobRow[] }>("/admin/jobs", { params })
      .then((r) => r.data),
};
