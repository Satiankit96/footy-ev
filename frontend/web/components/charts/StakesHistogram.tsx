"use client";

import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface Props {
  stakes: string[]; // stake_gbp values serialised as strings
}

const N_BINS = 12;

interface Bin {
  label: string;
  count: number;
}

function buildBins(values: number[]): Bin[] {
  if (values.length === 0) return [];

  const min = Math.min(...values);
  const max = Math.max(...values);

  if (min === max) {
    return [{ label: `£${min.toFixed(2)}`, count: values.length }];
  }

  const width = (max - min) / N_BINS;
  const bins: Bin[] = Array.from({ length: N_BINS }, (_, i) => ({
    label: `£${(min + i * width).toFixed(2)}`,
    count: 0,
  }));

  for (const v of values) {
    const idx = Math.min(Math.floor((v - min) / width), N_BINS - 1);
    bins[idx].count += 1;
  }

  return bins;
}

export default function StakesHistogram({ stakes }: Props) {
  const nums = stakes.map((s) => parseFloat(s)).filter((v) => !isNaN(v) && v > 0);
  const bins = buildBins(nums);

  if (bins.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
        No stake data yet.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={bins} margin={{ top: 4, right: 4, left: 0, bottom: 28 }}>
        <XAxis
          dataKey="label"
          tick={{ fontSize: 10 }}
          angle={-40}
          textAnchor="end"
          interval={0}
        />
        <YAxis allowDecimals={false} tick={{ fontSize: 10 }} />
        <Tooltip contentStyle={{ fontSize: 11 }} />
        <Bar dataKey="count" name="Bets" radius={[2, 2, 0, 0]}>
          {bins.map((_, idx) => (
            <Cell key={idx} fill="hsl(var(--primary))" fillOpacity={0.7} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
