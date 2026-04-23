import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { adminApi } from "../api";
import { Card, StatCard, Td, Th } from "../components/ui";

const fmtNum = (n: number) => n.toLocaleString();
const fmtUsd = (n: number) => `$${n.toFixed(4)}`;
const fmtPct = (n: number) => `${(n * 100).toFixed(1)}%`;
const hrs = (v: string) => v.slice(11, 13);
const mins = (v: string) => v.slice(11, 16);

const PROVIDER_COLORS = ["#4f8cff", "#6fe0a2", "#e7cc6f", "#e07f8e", "#c084fc"];

const tooltip = { background: "#151821", border: "1px solid #22262f" } as const;

export default function Overview() {
  const overview = useQuery({
    queryKey: ["overview"],
    queryFn: adminApi.overview,
    refetchInterval: 10_000,
  });
  const latency = useQuery({
    queryKey: ["latency"],
    queryFn: adminApi.latency,
    refetchInterval: 30_000,
  });
  const errors = useQuery({
    queryKey: ["errors"],
    queryFn: adminApi.errors,
    refetchInterval: 30_000,
  });
  const tokens = useQuery({
    queryKey: ["tokens"],
    queryFn: adminApi.tokensByProvider,
    refetchInterval: 60_000,
  });
  const costs = useQuery({
    queryKey: ["costs"],
    queryFn: adminApi.costByKey,
    refetchInterval: 60_000,
  });
  const rateLimits = useQuery({
    queryKey: ["rate-limits"],
    queryFn: adminApi.rateLimits,
    refetchInterval: 30_000,
  });

  if (overview.isLoading) return <p className="text-muted">Loading…</p>;
  if (overview.error || !overview.data)
    return <p className="text-[#e07f8e]">Failed to load overview.</p>;
  const d = overview.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="text-xs text-muted">Live SQL aggregations over usage_logs.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Requests (24h)" value={fmtNum(d.totals_24h.requests)} />
        <StatCard label="Cache hit rate" value={fmtPct(d.totals_24h.cache_hit_rate)} />
        <StatCard label="p95 latency" value={`${d.totals_24h.p95_latency_ms} ms`} />
        <StatCard
          label="Cost (24h)"
          value={fmtUsd(d.totals_24h.cost_usd)}
          sub={`${fmtNum(d.totals_24h.tokens)} tokens`}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="p-4">
          <h2 className="text-sm font-medium mb-3">Requests / minute (1h)</h2>
          <div className="h-56">
            <ResponsiveContainer>
              <LineChart data={d.requests_per_minute_1h}>
                <CartesianGrid stroke="#22262f" />
                <XAxis dataKey="minute" tick={{ fill: "#8b93a7", fontSize: 11 }} tickFormatter={mins} />
                <YAxis tick={{ fill: "#8b93a7", fontSize: 11 }} />
                <Tooltip contentStyle={tooltip} />
                <Line type="monotone" dataKey="count" stroke="#4f8cff" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="p-4">
          <h2 className="text-sm font-medium mb-3">Cache hits / hour (24h)</h2>
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={d.cache_hourly_24h}>
                <CartesianGrid stroke="#22262f" />
                <XAxis dataKey="hour" tick={{ fill: "#8b93a7", fontSize: 11 }} tickFormatter={hrs} />
                <YAxis tick={{ fill: "#8b93a7", fontSize: 11 }} />
                <Tooltip contentStyle={tooltip} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="exact" stackId="c" fill="#6fe0a2" />
                <Bar dataKey="semantic" stackId="c" fill="#7faaff" />
                <Bar dataKey="none" stackId="c" fill="#3a3f4c" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="p-4">
          <h2 className="text-sm font-medium mb-3">Latency percentiles (24h)</h2>
          <div className="h-56">
            <ResponsiveContainer>
              <LineChart data={latency.data?.series ?? []}>
                <CartesianGrid stroke="#22262f" />
                <XAxis dataKey="t" tick={{ fill: "#8b93a7", fontSize: 11 }} tickFormatter={hrs} />
                <YAxis tick={{ fill: "#8b93a7", fontSize: 11 }} unit=" ms" />
                <Tooltip contentStyle={tooltip} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line type="monotone" dataKey="p50" stroke="#6fe0a2" dot={false} />
                <Line type="monotone" dataKey="p95" stroke="#e7cc6f" dot={false} />
                <Line type="monotone" dataKey="p99" stroke="#e07f8e" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="p-4">
          <h2 className="text-sm font-medium mb-3">Errors & rate-limits / hour (24h)</h2>
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={errors.data?.series ?? []}>
                <CartesianGrid stroke="#22262f" />
                <XAxis dataKey="t" tick={{ fill: "#8b93a7", fontSize: 11 }} tickFormatter={hrs} />
                <YAxis tick={{ fill: "#8b93a7", fontSize: 11 }} />
                <Tooltip contentStyle={tooltip} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="errors" fill="#e07f8e" stackId="e" />
                <Bar dataKey="rate_limited" fill="#e7cc6f" stackId="e" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <Card className="p-4">
        <h2 className="text-sm font-medium mb-3">Tokens by provider (7d)</h2>
        <div className="h-56">
          <ResponsiveContainer>
            <BarChart data={tokens.data?.series ?? []}>
              <CartesianGrid stroke="#22262f" />
              <XAxis dataKey="d" tick={{ fill: "#8b93a7", fontSize: 11 }} tickFormatter={(v: string) => v.slice(5, 10)} />
              <YAxis tick={{ fill: "#8b93a7", fontSize: 11 }} />
              <Tooltip contentStyle={tooltip} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {(tokens.data?.providers ?? []).map((p, i) => (
                <Bar
                  key={p}
                  dataKey={p}
                  stackId="tk"
                  fill={PROVIDER_COLORS[i % PROVIDER_COLORS.length]}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-medium p-4 pb-2">Top cost by API key (7d)</h2>
        <table className="w-full">
          <thead>
            <tr>
              <Th>Name</Th>
              <Th>Prefix</Th>
              <Th>Requests</Th>
              <Th>Tokens</Th>
              <Th>Cost</Th>
            </tr>
          </thead>
          <tbody>
            {(costs.data?.rows ?? []).map((r) => (
              <tr key={r.prefix}>
                <Td>{r.name}</Td>
                <Td className="font-mono text-xs text-muted">{r.prefix}</Td>
                <Td>{r.requests.toLocaleString()}</Td>
                <Td>{r.tokens.toLocaleString()}</Td>
                <Td>${r.cost_usd.toFixed(5)}</Td>
              </tr>
            ))}
            {(costs.data?.rows ?? []).length === 0 && (
              <tr>
                <Td><span className="text-muted">no data yet</span></Td>
                <Td></Td><Td></Td><Td></Td><Td></Td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Card className="p-4">
        <h2 className="text-sm font-medium mb-3">Rate-limit rejections / hour (24h)</h2>
        <div className="h-40">
          <ResponsiveContainer>
            <LineChart data={rateLimits.data?.series ?? []}>
              <CartesianGrid stroke="#22262f" />
              <XAxis dataKey="t" tick={{ fill: "#8b93a7", fontSize: 11 }} tickFormatter={hrs} />
              <YAxis tick={{ fill: "#8b93a7", fontSize: 11 }} />
              <Tooltip contentStyle={tooltip} />
              <Line type="monotone" dataKey="rejections" stroke="#e7cc6f" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  );
}
