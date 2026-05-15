"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  Cell,
  ResponsiveContainer,
} from "recharts";
import type { ClvRollingPoint } from "@/lib/api/hooks";

interface HistBin {
  center: number;
  count: number;
}

function buildHistogram(points: ClvRollingPoint[], bins: number = 20): HistBin[] {
  if (points.length === 0) return [];
  const values = points.map((p) => p.clv_pct);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 0.01;
  const binWidth = range / bins;

  const counts = new Array<number>(bins).fill(0);
  for (const v of values) {
    const i = Math.min(bins - 1, Math.floor((v - min) / binWidth));
    counts[i]++;
  }
  return counts.map((count, i) => ({
    center: min + (i + 0.5) * binWidth,
    count,
  }));
}

export default function ClvHistogram({ data }: { data: ClvRollingPoint[] }) {
  if (data.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
        No CLV data yet.
      </div>
    );
  }

  const bins = buildHistogram(data);

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={bins} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis
          dataKey="center"
          tickFormatter={(v: number) => `${(v * 100).toFixed(1)}%`}
          tick={{ fontSize: 10 }}
        />
        <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
        <Tooltip
          formatter={(count: number) => [count, "bets"]}
          labelFormatter={(v: number) => `CLV ≈ ${(v * 100).toFixed(2)}%`}
          contentStyle={{ fontSize: 12 }}
        />
        <ReferenceLine x={0} stroke="hsl(var(--muted-foreground))" strokeDasharray="4 2" />
        <Bar dataKey="count" name="Bets" radius={[3, 3, 0, 0]}>
          {bins.map((bin, i) => (
            <Cell
              key={i}
              fill={bin.center >= 0 ? "hsl(142 71% 45%)" : "hsl(0 84% 60%)"}
              fillOpacity={0.85}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
