"use client";

import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { BankrollPoint } from "@/lib/api/hooks";

interface Props {
  data: BankrollPoint[];
}

export default function BankrollSparkline({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="flex h-24 items-center justify-center text-sm text-muted-foreground">
        No bankroll history yet.
      </div>
    );
  }

  const chartData = data.map((p) => ({
    decided_at: p.decided_at,
    bankroll: parseFloat(p.bankroll),
  }));

  return (
    <ResponsiveContainer width="100%" height={100}>
      <AreaChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 4 }}>
        <XAxis dataKey="decided_at" hide />
        <YAxis domain={["auto", "auto"]} hide />
        <Tooltip
          formatter={(val: number) => [`£${val.toFixed(2)}`, "Bankroll"]}
          labelFormatter={() => ""}
          contentStyle={{ fontSize: 11 }}
        />
        <Area
          type="monotone"
          dataKey="bankroll"
          stroke="hsl(var(--primary))"
          fill="hsl(var(--primary))"
          fillOpacity={0.15}
          strokeWidth={1.5}
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
