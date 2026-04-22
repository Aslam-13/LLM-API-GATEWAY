import { Link, NavLink, useNavigate } from "react-router-dom";
import { clearToken } from "../auth";
import type { ReactNode } from "react";

const navItems = [
  { to: "/", label: "Overview", end: true },
  { to: "/keys", label: "API Keys" },
  { to: "/usage", label: "Usage" },
  { to: "/jobs", label: "Jobs" },
];

export function Shell({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const onLogout = () => {
    clearToken();
    navigate("/login");
  };
  return (
    <div className="min-h-screen flex">
      <aside className="w-56 shrink-0 border-r border-border bg-panel flex flex-col">
        <Link to="/" className="px-5 py-5 text-lg font-semibold tracking-tight">
          llm-gateway
        </Link>
        <nav className="flex-1 px-2">
          {navItems.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                `block px-3 py-2 rounded-md text-sm my-0.5 ${
                  isActive
                    ? "bg-card text-white"
                    : "text-muted hover:text-white hover:bg-card/70"
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <button
          onClick={onLogout}
          className="m-3 text-xs text-muted hover:text-white text-left px-3 py-2"
        >
          Log out
        </button>
      </aside>
      <main className="flex-1 min-w-0 p-6">{children}</main>
    </div>
  );
}
