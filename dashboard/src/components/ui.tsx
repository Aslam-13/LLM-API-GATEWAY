import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`bg-card border border-border rounded-lg ${className}`}>{children}</div>
  );
}

export function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <Card className="p-5">
      <div className="text-xs uppercase tracking-wider text-muted">{label}</div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
      {sub && <div className="mt-1 text-xs text-muted">{sub}</div>}
    </Card>
  );
}

export function Pill({
  children,
  tone = "default",
}: {
  children: ReactNode;
  tone?: "default" | "ok" | "warn" | "err" | "info";
}) {
  const colors: Record<string, string> = {
    default: "bg-[#22262f] text-[#c6cad4]",
    ok: "bg-[#0f3e28] text-[#6fe0a2]",
    warn: "bg-[#3e330f] text-[#e7cc6f]",
    err: "bg-[#3e0f1a] text-[#e07f8e]",
    info: "bg-[#122746] text-[#7faaff]",
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${colors[tone]}`}
    >
      {children}
    </span>
  );
}

export function Button({
  children,
  variant = "default",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "primary" | "danger" | "ghost";
}) {
  const variants: Record<string, string> = {
    default: "bg-card border border-border hover:bg-[#1d2029]",
    primary: "bg-accent text-white hover:bg-[#3d7bff]",
    danger: "bg-[#2a1119] border border-[#5a1a28] text-[#e07f8e] hover:bg-[#3a1621]",
    ghost: "text-muted hover:text-white",
  };
  return (
    <button
      {...props}
      className={`px-3 py-1.5 rounded text-sm transition-colors ${variants[variant]} ${
        props.className ?? ""
      }`}
    />
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full bg-panel border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent ${
        props.className ?? ""
      }`}
    />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`bg-panel border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent ${
        props.className ?? ""
      }`}
    />
  );
}

export function Th({ children }: { children?: ReactNode }) {
  return (
    <th className="text-left text-[11px] uppercase tracking-wider text-muted font-medium px-3 py-2 border-b border-border">
      {children}
    </th>
  );
}

export function Td({ children, className = "" }: { children?: ReactNode; className?: string }) {
  return (
    <td className={`px-3 py-2 border-b border-border text-sm ${className}`}>{children}</td>
  );
}
