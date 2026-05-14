"use client";

import { BarChart3 } from "lucide-react";

export default function DashboardPage() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 text-muted-foreground">
      <BarChart3 size={48} strokeWidth={1} />
      <p className="text-lg">Dashboard tiles coming in Stage 3+</p>
    </div>
  );
}
