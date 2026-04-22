import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { adminApi } from "../api";
import { Button, Card, Input, Pill, Td, Th } from "../components/ui";
import { Modal } from "../components/Modal";

export default function Keys() {
  const qc = useQueryClient();
  const keys = useQuery({ queryKey: ["keys"], queryFn: adminApi.listKeys });
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newAdmin, setNewAdmin] = useState(false);
  const [createdPlain, setCreatedPlain] = useState<string | null>(null);

  const createM = useMutation({
    mutationFn: adminApi.createKey,
    onSuccess: (data) => {
      setCreatedPlain(data.plaintext);
      setCreateOpen(false);
      setNewName("");
      setNewEmail("");
      setNewAdmin(false);
      qc.invalidateQueries({ queryKey: ["keys"] });
    },
  });

  const revokeM = useMutation({
    mutationFn: (id: string) => adminApi.revokeKey(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["keys"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">API Keys</h1>
          <p className="text-xs text-muted">Gateway-scoped auth tokens.</p>
        </div>
        <Button variant="primary" onClick={() => setCreateOpen(true)}>+ New key</Button>
      </div>

      <Card>
        <table className="w-full">
          <thead><tr>
            <Th>Name</Th><Th>Prefix</Th><Th>Email</Th><Th>Role</Th>
            <Th>Created</Th><Th>Last used</Th><Th>Status</Th><Th></Th>
          </tr></thead>
          <tbody>
            {keys.data?.map((k) => (
              <tr key={k.id}>
                <Td>{k.name}</Td>
                <Td className="font-mono text-xs">{k.prefix}</Td>
                <Td className="text-muted">{k.email || "—"}</Td>
                <Td>{k.admin ? <Pill tone="info">admin</Pill> : <Pill>user</Pill>}</Td>
                <Td className="text-muted text-xs">{k.created_at?.slice(0, 10)}</Td>
                <Td className="text-muted text-xs">{k.last_used_at?.replace("T", " ").slice(0, 19) || "—"}</Td>
                <Td>
                  {k.revoked_at ? <Pill tone="err">revoked</Pill> : <Pill tone="ok">active</Pill>}
                </Td>
                <Td>
                  {!k.revoked_at && (
                    <Button
                      variant="danger"
                      onClick={() => {
                        if (confirm(`Revoke key "${k.name}"?`)) revokeM.mutate(k.id);
                      }}
                    >Revoke</Button>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
        {keys.isLoading && <div className="p-4 text-muted text-sm">Loading…</div>}
      </Card>

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="Create API key">
        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted block mb-1">Name</label>
            <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="marketing-team" />
          </div>
          <div>
            <label className="text-xs text-muted block mb-1">Email (optional)</label>
            <Input value={newEmail} onChange={(e) => setNewEmail(e.target.value)} placeholder="team@example.com" />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={newAdmin}
              onChange={(e) => setNewAdmin(e.target.checked)}
            />
            admin
          </label>
          <div className="flex justify-end gap-2 pt-2">
            <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={!newName || createM.isPending}
              onClick={() =>
                createM.mutate({
                  name: newName,
                  email: newEmail || undefined,
                  admin: newAdmin,
                })
              }
            >
              {createM.isPending ? "Creating…" : "Create"}
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={Boolean(createdPlain)}
        onClose={() => setCreatedPlain(null)}
        title="Key created — copy it now"
      >
        <p className="text-xs text-muted mb-2">
          This key will never be shown again. Copy it before closing.
        </p>
        <pre className="bg-panel border border-border rounded p-3 font-mono text-xs break-all whitespace-pre-wrap">
          {createdPlain}
        </pre>
        <div className="flex justify-end mt-3">
          <Button
            variant="primary"
            onClick={() => {
              if (createdPlain) navigator.clipboard.writeText(createdPlain);
            }}
          >Copy</Button>
        </div>
      </Modal>
    </div>
  );
}
