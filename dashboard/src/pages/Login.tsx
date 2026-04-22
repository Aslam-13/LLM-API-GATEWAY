import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { setToken } from "../auth";
import { adminApi } from "../api";
import { Button, Input } from "../components/ui";

export default function Login() {
  const navigate = useNavigate();
  const [key, setKey] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    setToken(key.trim());
    try {
      await adminApi.me();
      navigate("/");
    } catch (e) {
      setErr("Invalid admin key");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-panel">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm bg-card border border-border rounded-lg p-6"
      >
        <h1 className="text-lg font-semibold mb-1">llm-gateway</h1>
        <p className="text-xs text-muted mb-5">Paste an admin API key.</p>
        <Input
          type="password"
          placeholder="sk-gw-live-…"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          autoFocus
        />
        {err && <p className="text-[#e07f8e] text-xs mt-2">{err}</p>}
        <Button
          type="submit"
          variant="primary"
          className="w-full mt-4"
          disabled={!key || busy}
        >
          {busy ? "Checking…" : "Log in"}
        </Button>
      </form>
    </div>
  );
}
