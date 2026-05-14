"use client";

import { Activity, BarChart3 } from "lucide-react";
import { useHealth } from "@/lib/api/hooks";

export default function DashboardPage() {
  const { data: health, isLoading } = useHealth();

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 text-muted-foreground">
      <BarChart3 size={48} strokeWidth={1} />
      <p className="text-lg">Dashboard tiles coming in Stage 3+</p>
      <div className="flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm">
        <Activity size={14} />
        {isLoading ? (
          <span>Checking API...</span>
        ) : health ? (
          <span>
            API {health.status} &middot; v{health.version} &middot; uptime{" "}
            {health.uptime_s}s
            {health.active_venue && ` · ${health.active_venue}`}
          </span>
        ) : (
          <span className="text-destructive">API unreachable</span>
        )}
      </div>
    </div>
  );
}
