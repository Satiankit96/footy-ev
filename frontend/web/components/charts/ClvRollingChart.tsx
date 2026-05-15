"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  Brush,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { ClvRollingPoint } from "@/lib/api/hooks";

interface Props {
  data100: ClvRollingPoint[];
  data500: ClvRollingPoint[];
}

function clvFormatter(value: number) {
  return `${(value * 100).toFixed(2)}%`;
}

export default function ClvRollingChart({ data100, data500 }: Props) {
  if (data100.length === 0 && data500.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
        No CLV data — run backfill after settlement.
      </div>
    );
  }

  // Merge into unified dataset by bet_index (primary) and decided_at
  const indexSet = new Set([
    ...data100.map((d) => d.bet_index),
    ...data500.map((d) => d.bet_index),
  ]);
  const map100 = new Map(data100.map((d) => [d.bet_index, d]));
  const map500 = new Map(data500.map((d) => [d.bet_index, d]));

  const merged = Array.from(indexSet)
    .sort((a, b) => a - b)
    .map((idx) => ({
      bet_index: idx,
      rolling_100: map100.get(idx)?.rolling_clv ?? null,
      rolling_500: map500.get(idx)?.rolling_clv ?? null,
      cumulative: map100.get(idx)?.cumulative_clv ?? map500.get(idx)?.cumulative_clv ?? null,
    }));

  const showBrush = merged.length > 50;

  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={merged} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis
          dataKey="bet_index"
          tick={{ fontSize: 11 }}
          label={{ value: "Bet #", position: "insideBottomRight", offset: -4, fontSize: 11 }}
        />
        <YAxis
          tickFormatter={clvFormatter}
          tick={{ fontSize: 11 }}
          domain={["auto", "auto"]}
        />
        <Tooltip
          formatter={(val: number) => clvFormatter(val)}
          labelFormatter={(label) => `Bet #${label}`}
          contentStyle={{ fontSize: 12 }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <ReferenceLine y={0} stroke="hsl(var(--muted-foreground))" strokeDasharray="4 2" />
        <Line
          type="monotone"
          dataKey="rolling_100"
          name="100-bet rolling"
          stroke="hsl(var(--primary))"
          dot={false}
          strokeWidth={2}
          connectNulls
        />
        <Line
          type="monotone"
          dataKey="rolling_500"
          name="500-bet rolling"
          stroke="hsl(var(--accent))"
          dot={false}
          strokeWidth={1.5}
          strokeDasharray="5 3"
          connectNulls
        />
        <Line
          type="monotone"
          dataKey="cumulative"
          name="cumulative"
          stroke="hsl(var(--muted-foreground))"
          dot={false}
          strokeWidth={1}
          strokeDasharray="2 4"
          connectNulls
        />
        {showBrush && <Brush dataKey="bet_index" height={20} travellerWidth={6} />}
      </LineChart>
    </ResponsiveContainer>
  );
}
