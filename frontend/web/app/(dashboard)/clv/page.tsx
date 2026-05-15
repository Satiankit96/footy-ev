"use client";

import { useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useClvRolling,
  useClvSources,
  useBetsSummary,
} from "@/lib/api/hooks";
import type { ClvSourceItem } from "@/lib/api/hooks";
import ClvRollingChart from "@/components/charts/ClvRollingChart";
import ClvHistogram from "@/components/charts/ClvHistogram";
import { BackfillModal } from "@/components/clv/BackfillModal";

export default function ClvPage() {
  const [showBackfill, setShowBackfill] = useState(false);

  const { data: rolling100, isLoading: l100, refetch: r100 } = useClvRolling(100);
  const { data: rolling500, isLoading: l500, refetch: r500 } = useClvRolling(500);
  const { data: sources, isLoading: lSources } = useClvSources();
  const { data: summary } = useBetsSummary("all");

  function handleRefresh() {
    void r100();
    void r500();
  }

  const isLoading = l100 || l500;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">CLV Analytics</h1>
          <p className="text-sm text-muted-foreground">
            Closing-line value across all settled paper bets
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={handleRefresh} disabled={isLoading}>
            {isLoading ? (
              <Loader2 size={14} className="mr-2 animate-spin" />
            ) : (
              <RefreshCw size={14} className="mr-2" />
            )}
            Refresh
          </Button>
          <Button size="sm" onClick={() => setShowBackfill(true)}>
            <RefreshCw size={14} className="mr-2" />
            Backfill CLV
          </Button>
        </div>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <SummaryCard
            label="Total Bets"
            value={String(summary.total_bets)}
          />
          <SummaryCard
            label="Mean CLV"
            value={
              summary.mean_clv != null
                ? `${(summary.mean_clv * 100).toFixed(2)}%`
                : "—"
            }
            positive={summary.mean_clv != null && summary.mean_clv >= 0}
            negative={summary.mean_clv != null && summary.mean_clv < 0}
          />
          <SummaryCard label="ROI" value={`${(summary.roi * 100).toFixed(2)}%`} />
          <SummaryCard label="Total P&L" value={`£${summary.total_pnl}`} />
        </div>
      )}

      {/* Rolling CLV chart */}
      <Card>
        <CardHeader>
          <CardTitle>Rolling CLV</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex h-48 items-center justify-center">
              <Loader2 size={20} className="animate-spin text-muted-foreground" />
            </div>
          ) : (
            <ClvRollingChart
              data100={rolling100 ?? []}
              data500={rolling500 ?? []}
            />
          )}
        </CardContent>
      </Card>

      {/* CLV histogram */}
      <Card>
        <CardHeader>
          <CardTitle>CLV Distribution</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex h-40 items-center justify-center">
              <Loader2 size={20} className="animate-spin text-muted-foreground" />
            </div>
          ) : (
            <ClvHistogram data={rolling100 ?? []} />
          )}
        </CardContent>
      </Card>

      {/* CLV by source */}
      <Card>
        <CardHeader>
          <CardTitle>CLV by Benchmark Source</CardTitle>
        </CardHeader>
        <CardContent>
          {lSources ? (
            <div className="flex h-24 items-center justify-center">
              <Loader2 size={16} className="animate-spin text-muted-foreground" />
            </div>
          ) : (sources ?? []).length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No settled bets with CLV data yet.
            </p>
          ) : (
            <SourcesTable sources={sources!} />
          )}
        </CardContent>
      </Card>

      {showBackfill && <BackfillModal onClose={() => setShowBackfill(false)} />}
    </div>
  );
}

function SummaryCard({
  label,
  value,
  positive = false,
  negative = false,
}: {
  label: string;
  value: string;
  positive?: boolean;
  negative?: boolean;
}) {
  const cls = positive
    ? "text-green-500"
    : negative
      ? "text-red-500"
      : "text-foreground";
  return (
    <div className="rounded-lg border border-border p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`mt-1 text-2xl font-bold tabular-nums ${cls}`}>{value}</p>
    </div>
  );
}

function SourcesTable({ sources }: { sources: ClvSourceItem[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted-foreground">
            <th className="pb-2 font-medium">Source</th>
            <th className="pb-2 text-right font-medium">Bets</th>
            <th className="pb-2 text-right font-medium">Mean CLV</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((s) => (
            <tr key={s.source} className="border-b border-border/40">
              <td className="py-2 font-mono text-xs capitalize">{s.source}</td>
              <td className="py-2 text-right font-mono text-xs">{s.n_bets}</td>
              <td
                className={`py-2 text-right font-mono text-xs font-medium ${
                  s.mean_clv == null
                    ? "text-muted-foreground"
                    : s.mean_clv >= 0
                      ? "text-green-500"
                      : "text-red-500"
                }`}
              >
                {s.mean_clv != null ? `${(s.mean_clv * 100).toFixed(2)}%` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
