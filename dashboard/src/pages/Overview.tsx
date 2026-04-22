import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { adminApi } from "../api";
import { Card, StatCard } from "../components/ui";

const fmtNum = (n: number) => n.toLocaleString();
const fmtUsd = (n: number) => `$${n.toFixed(4)}`;
const fmtPct = (n: number) => `${(n * 100).toFixed(1)}%`;

export default function Overview() {
  const q = useQuery({
    queryKey: ["overview"],
    queryFn: adminApi.overview,
    refetchInterval: 10_000,
  });

  if (q.isLoading) return <p className="text-muted">Loading…</p>;
  if (q.error || !q.data) return <p className="text-[#e07f8e]">Failed to load overview.</p>;
  const d = q.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="text-xs text-muted">Last 24 hours · auto-refresh 10s</p>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Requests" value={fmtNum(d.totals_24h.requests)} />
        <StatCard label="Cache hit rate" value={fmtPct(d.totals_24h.cache_hit_rate)} />
        <StatCard label="p95 latency" value={`${d.totals_24h.p95_latency_ms} ms`} />
        <StatCard label="Cost" value={fmtUsd(d.totals_24h.cost_usd)} sub={`${fmtNum(d.totals_24h.tokens)} tokens`} />
      </div>
      <Card className="p-4">
        <h2 className="text-sm font-medium mb-3">Requests / minute (last hour)</h2>
        <div className="h-56">
          <ResponsiveContainer>
            <LineChart data={d.requests_per_minute_1h}>
              <CartesianGrid stroke="#22262f" />
              <XAxis dataKey="minute" tick={{ fill: "#8b93a7", fontSize: 11 }} tickFormatter={(v) => v.slice(11, 16)} />
              <YAxis tick={{ fill: "#8b93a7", fontSize: 11 }} />
              <Tooltip contentStyle={{ background: "#151821", border: "1px solid #22262f" }} />
              <Line type="monotone" dataKey="count" stroke="#4f8cff" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card className="p-4">
        <h2 className="text-sm font-medium mb-3">Cache hits per hour (24h)</h2>
        <div className="h-56">
          <ResponsiveContainer>
            <BarChart data={d.cache_hourly_24h}>
              <CartesianGrid stroke="#22262f" />
              <XAxis dataKey="hour" tick={{ fill: "#8b93a7", fontSize: 11 }} tickFormatter={(v) => v.slice(11, 13)} />
              <YAxis tick={{ fill: "#8b93a7", fontSize: 11 }} />
              <Tooltip contentStyle={{ background: "#151821", border: "1px solid #22262f" }} />
              <Bar dataKey="exact" stackId="c" fill="#6fe0a2" />
              <Bar dataKey="semantic" stackId="c" fill="#7faaff" />
              <Bar dataKey="none" stackId="c" fill="#3a3f4c" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  );
}
