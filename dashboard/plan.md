# Dashboard — Internal Ops Tool

React + Vite + TypeScript + Tailwind. Single-tenant. Admin-only auth (paste admin API key → stored in localStorage → sent as `Authorization: Bearer …`). No signup / no marketing / no billing. Looks like Linear / an internal admin panel, not a SaaS landing page.

Hosted at `dashboard.yourdomain.com` (Nginx serves the built static bundle from Phase 15).

---

## Stack
- Vite + React 18 + TypeScript
- Tailwind CSS
- `@tanstack/react-query` (server state, auto-refresh)
- `axios` (one shared client with auth header)
- `recharts` (charts)
- `react-router-dom` (routes)
- No state library — React Query covers it

## Pages (5 total)

### `/login`
- One input: admin API key. Store in localStorage. Redirect to `/`.
- Invalid key → shake + red error.

### `/` — Overview
- Big stat cards: requests today, cost today, cache hit rate, p95 latency.
- Line chart: requests/min over last hour.
- Stacked bar: cache hits split (none / exact / semantic) over last 24h.
- Auto-refresh every 10s.

### `/keys` — API Keys
- Table: name, prefix, admin?, created_at, last_used, revoked?
- Create key: modal (name, email, admin checkbox) → POST returns plaintext once → copy-to-clipboard banner.
- Revoke: confirm modal → soft-delete (sets `revoked_at`).

### `/usage` — Per-Key Usage
- Filter: api_key dropdown, date range.
- Table: request_id, model, provider, tokens, cost, latency, cache_hit, status.
- Pagination (server-side, 50/page).
- Charts above table: requests/day, tokens/day, cost/day for selected key.

### `/jobs` — Async Jobs
- Table of recent `Job` rows: id, kind, status pill, created_at, finished_at.
- Row click → side drawer with input/result JSON.
- Auto-refresh running jobs every 5s.

## Admin endpoints the dashboard needs (backend, `app/api/admin/`)

| Method + path | Purpose |
|---|---|
| `GET /admin/me` | verify admin key, return profile |
| `GET /admin/stats/overview?window=…` | cards + cache-hit stacked chart data |
| `GET /admin/keys` | list all keys |
| `POST /admin/keys` | create key → returns plaintext once |
| `DELETE /admin/keys/{id}` | revoke (soft) |
| `GET /admin/usage?api_key_id=&from=&to=&limit=&offset=` | paginated UsageLog + aggregate totals |
| `GET /admin/jobs?status=&limit=&offset=` | paginated jobs |

All require `require_admin_key` from `app/auth/middleware.py`.

## Folder layout
```
dashboard/
├── index.html
├── package.json / tsconfig.json / vite.config.ts
├── tailwind.config.ts
├── src/
│   ├── main.tsx / App.tsx / router.tsx
│   ├── api/              axios client + typed endpoint fns + types
│   ├── auth/             token storage, ProtectedRoute, useAuth
│   ├── components/       StatCard, DataTable, ChartCard, Modal, Pill, Drawer
│   ├── pages/            Login, Overview, Keys, Usage, Jobs
│   ├── hooks/            useKeys, useUsage, useJobs (react-query wrappers)
│   └── styles.css
└── dist/                 built bundle (Nginx serves this in prod)
```

## Dev / prod wiring
- Dev: `npm run dev` on :5173. Vite proxy `/admin` and `/v1` → `http://localhost:8000`.
- Prod: `npm run build` → `dist/`. Nginx vhost `dashboard.yourdomain.com` serves `dist/`, proxies `/admin` + `/v1` to `api.yourdomain.com`.
- Env: `VITE_API_BASE_URL` (empty in dev → uses proxy; full URL in prod).

## What we're NOT building (internal tool scope)
- No multi-user login / invites / SSO.
- No org / team / tenant concept.
- No billing / plan tiers / Stripe.
- No public signup.
- No docs page / marketing.
- No per-request PII redaction toggles.
- No multi-language / dark mode polish beyond default.

## Rough time budget (~6h)
1. Scaffold + auth + router + shared axios client — 1h
2. Login + ProtectedRoute + Overview cards + one chart — 1.5h
3. Keys page (list, create, revoke) — 1.5h
4. Usage page (filter + table + charts) — 1.5h
5. Jobs page + polish — 0.5h

## Definition of done
- Log in with admin key → see overview with real data flowing from a running backend.
- Create a new user key from UI → use it in a curl → see it in Usage.
- Kick off `/v1/embeddings/batch` via curl → row appears on Jobs page, status transitions live.
- Build + serve `dist/` under Nginx at `dashboard.yourdomain.com`.
