import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { adminApi } from "../api";
import { Card, Pill, Select, StatCard, Td, Th } from "../components/ui";

const DAYS = [1, 3, 7, 14, 30];

export default function Usage() {
  const [apiKeyId, setApiKeyId] = useState<string>("");
  const [days, setDays] = useState(7);
  const [page, setPage] = useState(0);
  const limit = 50;

  const keysQ = useQuery({ queryKey: ["keys"], queryFn: adminApi.listKeys });

  const from = useMemo(
    () => new Date(Date.now() - days * 86400_000).toISOString(),
    [days]
  );

  const q = useQuery({
    queryKey: ["usage", apiKeyId, from, page],
    queryFn: () =>
      adminApi.usage({
        api_key_id: apiKeyId || undefined,
        from,
        limit,
        offset: page * limit,
      }),
  });

  const d = q.data;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Usage</h1>
          <p className="text-xs text-muted">Aggregated from UsageLog.</p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={apiKeyId} onChange={(e) => { setApiKeyId(e.target.value); setPage(0); }}>
            <option value="">All keys</option>
            {keysQ.data?.map((k) => (
              <option key={k.id} value={k.id}>{k.name} · {k.prefix}</option>
            ))}
          </Select>
          <Select value={days} onChange={(e) => { setDays(Number(e.target.value)); setPage(0); }}>
            {DAYS.map((d) => (
              <option key={d} value={d}>Last {d}d</option>
            ))}
          </Select>
        </div>
      </div>

      {d && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Requests" value={d.aggregate.requests.toLocaleString()} />
            <StatCard label="Tokens" value={d.aggregate.tokens.toLocaleString()} />
            <StatCard label="Cost" value={`$${d.aggregate.cost_usd.toFixed(4)}`} />
            <StatCard label="Avg latency" value={`${d.aggregate.avg_latency_ms} ms`} />
          </div>
          <Card className="p-4">
            <h2 className="text-sm font-medium mb-3">Daily</h2>
            <div className="h-56">
              <ResponsiveContainer>
                <BarChart data={d.daily}>
                  <CartesianGrid stroke="#22262f" />
                  <XAxis dataKey="day" tick={{ fill: "#8b93a7", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#8b93a7", fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: "#151821", border: "1px solid #22262f" }} />
                  <Bar dataKey="requests" fill="#4f8cff" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <Card>
            <table className="w-full">
              <thead><tr>
                <Th>When</Th><Th>Model</Th><Th>Provider</Th><Th>Cache</Th>
                <Th>Tokens</Th><Th>Cost</Th><Th>Latency</Th><Th>Status</Th>
              </tr></thead>
              <tbody>
                {d.rows.map((r) => (
                  <tr key={r.id}>
                    <Td className="text-xs text-muted">{r.created_at?.replace("T", " ").slice(0, 19)}</Td>
                    <Td className="font-mono text-xs">{r.model}</Td>
                    <Td>{r.provider}</Td>
                    <Td>
                      <Pill tone={r.cache_hit === "exact" ? "ok" : r.cache_hit === "semantic" ? "info" : "default"}>
                        {r.cache_hit}
                      </Pill>
                    </Td>
                    <Td>{r.total_tokens}</Td>
                    <Td>${r.cost_usd.toFixed(5)}</Td>
                    <Td>{r.latency_ms} ms</Td>
                    <Td>
                      {r.status === "success" ? (
                        <Pill tone="ok">ok</Pill>
                      ) : (
                        <Pill tone="err">error</Pill>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="p-3 flex justify-between items-center text-xs text-muted">
              <span>{d.total} total · page {page + 1}</span>
              <div className="flex gap-2">
                <button
                  disabled={page === 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  className="px-2 py-1 rounded border border-border disabled:opacity-40"
                >Prev</button>
                <button
                  disabled={(page + 1) * limit >= d.total}
                  onClick={() => setPage((p) => p + 1)}
                  className="px-2 py-1 rounded border border-border disabled:opacity-40"
                >Next</button>
              </div>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
