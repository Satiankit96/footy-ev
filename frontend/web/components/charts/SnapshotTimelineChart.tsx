"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  Brush,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

export interface SnapshotPoint {
  captured_at: string;
  odds_decimal: number;
  venue: string;
  selection?: string;
}

interface Props {
  snapshots: SnapshotPoint[];
  className?: string;
}

const COLORS = [
  "#6366f1",
  "#22c55e",
  "#f59e0b",
  "#ec4899",
  "#14b8a6",
  "#f97316",
];

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function SnapshotTimelineChart({ snapshots, className }: Props) {
  if (!snapshots || snapshots.length === 0) {
    return (
      <div className={`flex items-center justify-center py-12 text-sm text-muted-foreground ${className ?? ""}`}>
        No snapshot data available.
      </div>
    );
  }

  // Group by venue — one line per venue
  const venues = Array.from(new Set(snapshots.map((s) => s.venue)));

  // Build unified timeline: each row is a captured_at timestamp with one value per venue
  const timeMap = new Map<string, Record<string, number>>();
  for (const snap of snapshots) {
    const key = snap.captured_at;
    if (!timeMap.has(key)) timeMap.set(key, {});
    timeMap.get(key)![snap.venue] = snap.odds_decimal;
  }

  const chartData = Array.from(timeMap.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([captured_at, values]) => ({ captured_at, ...values }));

  return (
    <div className={className}>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="currentColor" opacity={0.08} />
          <XAxis
            dataKey="captured_at"
            tickFormatter={formatTimestamp}
            tick={{ fontSize: 11 }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 11 }}
            tickLine={false}
            label={{ value: "Decimal odds", angle: -90, position: "insideLeft", offset: 10, style: { fontSize: 11 } }}
          />
          <Tooltip
            labelFormatter={(label: string) => formatTimestamp(label)}
            formatter={(value: number, name: string) => [value.toFixed(3), name]}
          />
          <Legend />
          {venues.map((venue, i) => (
            <Line
              key={venue}
              type="monotone"
              dataKey={venue}
              stroke={COLORS[i % COLORS.length]}
              dot={false}
              connectNulls
              strokeWidth={2}
            />
          ))}
          {chartData.length > 20 && <Brush dataKey="captured_at" height={20} />}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
