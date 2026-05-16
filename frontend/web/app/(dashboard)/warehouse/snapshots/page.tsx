"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, ChevronLeft, ChevronRight, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useWarehouseSnapshots } from "@/lib/api/hooks";
import type { SnapshotRow } from "@/lib/api/hooks";
import SnapshotTimelineChart from "@/components/charts/SnapshotTimelineChart";
import type { SnapshotPoint } from "@/components/charts/SnapshotTimelineChart";

const PAGE_SIZE = 100;

function formatTs(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-GB", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function SnapshotsPage() {
  const [fixtureId, setFixtureId] = useState("");
  const [market, setMarket] = useState("");
  const [venue, setVenue] = useState("");
  const [page, setPage] = useState(0);

  const offset = page * PAGE_SIZE;
  const { data, isLoading, refetch } = useWarehouseSnapshots({
    fixture_id: fixtureId || undefined,
    market: market || undefined,
    venue: venue || undefined,
    limit: PAGE_SIZE,
    offset,
  });

  const snapshots: SnapshotRow[] = data?.snapshots ?? [];
  const total = data?.total ?? 0;
  const pageCount = Math.ceil(total / PAGE_SIZE);

  const chartPoints: SnapshotPoint[] = snapshots
    .filter((s) => s.received_at !== null && s.odds_decimal !== null)
    .map((s) => ({
      captured_at: s.received_at!,
      odds_decimal: s.odds_decimal!,
      venue: s.venue,
      selection: s.selection,
    }));

  function applyFilters() {
    setPage(0);
    void refetch();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/warehouse">
          <Button variant="ghost" size="sm">
            <ArrowLeft size={14} />
            Back
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold">Odds Snapshots</h1>
          <p className="text-sm text-muted-foreground">
            Live odds timeline browser
          </p>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 pt-4">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">Fixture ID</label>
            <Input
              className="h-8 w-64 text-sm"
              placeholder="e.g. EPL|2025-2026|…"
              value={fixtureId}
              onChange={(e) => setFixtureId(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">Market</label>
            <Input
              className="h-8 w-40 text-sm"
              placeholder="e.g. match_result"
              value={market}
              onChange={(e) => setMarket(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">Venue</label>
            <Input
              className="h-8 w-32 text-sm"
              placeholder="e.g. betfair"
              value={venue}
              onChange={(e) => setVenue(e.target.value)}
            />
          </div>
          <Button size="sm" onClick={applyFilters} disabled={isLoading}>
            <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} />
            Filter
          </Button>
        </CardContent>
      </Card>

      {/* Timeline chart — only when fixture_id provided */}
      {fixtureId && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Odds Timeline</CardTitle>
          </CardHeader>
          <CardContent>
            <SnapshotTimelineChart snapshots={chartPoints} />
          </CardContent>
        </Card>
      )}

      {/* Snapshot table */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">
              {total > 0 ? `${total.toLocaleString()} snapshots` : "Snapshots"}
            </CardTitle>
            {pageCount > 1 && (
              <div className="flex items-center gap-2 text-sm">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                >
                  <ChevronLeft size={14} />
                </Button>
                <span className="text-muted-foreground">
                  {page + 1} / {pageCount}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                  disabled={page >= pageCount - 1}
                >
                  <ChevronRight size={14} />
                </Button>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 size={14} className="animate-spin" />
              Loading…
            </div>
          ) : snapshots.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No snapshots found. Apply a fixture ID filter to narrow results.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="pb-2 text-left font-medium text-muted-foreground">Received</th>
                    <th className="pb-2 text-left font-medium text-muted-foreground">Venue</th>
                    <th className="pb-2 text-left font-medium text-muted-foreground">Market</th>
                    <th className="pb-2 text-left font-medium text-muted-foreground">Selection</th>
                    <th className="pb-2 text-right font-medium text-muted-foreground">Odds</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {snapshots.map((s, i) => (
                    <tr key={i} className="hover:bg-muted/30">
                      <td className="py-1.5 text-muted-foreground">{formatTs(s.received_at)}</td>
                      <td className="py-1.5">{s.venue}</td>
                      <td className="py-1.5">{s.market}</td>
                      <td className="py-1.5">{s.selection}</td>
                      <td className="py-1.5 text-right tabular-nums">
                        {s.odds_decimal !== null ? s.odds_decimal.toFixed(3) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
