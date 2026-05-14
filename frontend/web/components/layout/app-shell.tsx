"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";

interface ShellData {
  venue: { name: string; base_url: string; is_demo: boolean } | null;
  circuit_breaker: { state: string; reason: string | null } | null;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [shell, setShell] = useState<ShellData | null>(null);

  useEffect(() => {
    fetch("/api/v1/shell")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: ShellData) => setShell(data))
      .catch(() => setShell(null));
  }, []);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar shell={shell} />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
