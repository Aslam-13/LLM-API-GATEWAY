import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { adminApi, type JobRow } from "../api";
import { Button, Card, Pill, Select, Td, Th } from "../components/ui";

const STATUS_TONES: Record<string, "ok" | "warn" | "err" | "info" | "default"> = {
  succeeded: "ok",
  failed: "err",
  running: "info",
  pending: "warn",
};

export default function Jobs() {
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<JobRow | null>(null);

  const q = useQuery({
    queryKey: ["jobs", status],
    queryFn: () => adminApi.jobs({ status: status || undefined, limit: 100 }),
    refetchInterval: 5_000,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Jobs</h1>
          <p className="text-xs text-muted">Async Celery tasks · auto-refresh 5s</p>
        </div>
        <Select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All</option>
          <option value="pending">Pending</option>
          <option value="running">Running</option>
          <option value="succeeded">Succeeded</option>
          <option value="failed">Failed</option>
        </Select>
      </div>

      <Card>
        <table className="w-full">
          <thead><tr>
            <Th>Id</Th><Th>Kind</Th><Th>Status</Th><Th>Created</Th>
            <Th>Started</Th><Th>Finished</Th><Th></Th>
          </tr></thead>
          <tbody>
            {q.data?.rows.map((j) => (
              <tr key={j.id}>
                <Td className="font-mono text-xs">{j.id.slice(0, 8)}…</Td>
                <Td>{j.kind}</Td>
                <Td><Pill tone={STATUS_TONES[j.status] ?? "default"}>{j.status}</Pill></Td>
                <Td className="text-xs text-muted">{j.created_at?.replace("T", " ").slice(0, 19)}</Td>
                <Td className="text-xs text-muted">{j.started_at?.replace("T", " ").slice(0, 19) || "—"}</Td>
                <Td className="text-xs text-muted">{j.finished_at?.replace("T", " ").slice(0, 19) || "—"}</Td>
                <Td><Button variant="ghost" onClick={() => setSelected(j)}>View</Button></Td>
              </tr>
            ))}
          </tbody>
        </table>
        {q.isLoading && <div className="p-4 text-muted text-sm">Loading…</div>}
      </Card>

      {selected && (
        <div
          className="fixed inset-0 bg-black/60 flex justify-end z-50"
          onClick={() => setSelected(null)}
        >
          <div
            className="w-[520px] bg-card border-l border-border h-full overflow-auto p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-start mb-4">
              <div>
                <h2 className="text-sm font-semibold">Job {selected.id.slice(0, 8)}…</h2>
                <p className="text-xs text-muted mt-1">{selected.kind} · {selected.status}</p>
              </div>
              <button onClick={() => setSelected(null)} className="text-muted hover:text-white text-lg">×</button>
            </div>
            <section className="mb-4">
              <h3 className="text-xs uppercase text-muted mb-1">Input</h3>
              <pre className="bg-panel border border-border rounded p-3 text-xs overflow-auto">
                {JSON.stringify(selected.input, null, 2)}
              </pre>
            </section>
            {selected.error && (
              <section className="mb-4">
                <h3 className="text-xs uppercase text-muted mb-1">Error</h3>
                <pre className="bg-[#2a1119] border border-[#5a1a28] text-[#e07f8e] rounded p-3 text-xs overflow-auto whitespace-pre-wrap">
                  {selected.error}
                </pre>
              </section>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
