"use client";

import { useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, Loader2, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useBets } from "@/lib/api/hooks";
import type { BetResponse } from "@/lib/api/hooks";

const PAGE_SIZE = 50;

const STATUS_OPTIONS = ["", "pending", "won", "lost", "void"];

function clvColor(clv: number | null): string {
  if (clv === null) return "text-muted-foreground";
  return clv >= 0 ? "text-green-500" : "text-red-500";
}

function formatClv(clv: number | null): string {
  if (clv === null) return "—";
  return `${(clv * 100).toFixed(2)}%`;
}

function formatAge(isoStr: string | null): string {
  if (!isoStr) return "—";
  const diffMs = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function BetsPage() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [status, setStatus] = useState(searchParams.get("status") ?? "");
  const [fixtureId, setFixtureId] = useState(searchParams.get("fixture_id") ?? "");
  const [venue, setVenue] = useState(searchParams.get("venue") ?? "");
  const [dateFrom, setDateFrom] = useState(searchParams.get("date_from") ?? "");
  const [dateTo, setDateTo] = useState(searchParams.get("date_to") ?? "");
  const [page, setPage] = useState(parseInt(searchParams.get("page") ?? "1", 10));

  const offset = (page - 1) * PAGE_SIZE;

  const { data, isLoading, isFetching, refetch } = useBets({
    status: status || undefined,
    fixture_id: fixtureId || undefined,
    venue: venue || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    limit: PAGE_SIZE,
    offset,
  });

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));

  function updateUrl(overrides: Record<string, string | number>) {
    const params = new URLSearchParams();
    const vals: Record<string, string | number> = {
      status,
      fixture_id: fixtureId,
      venue,
      date_from: dateFrom,
      date_to: dateTo,
      page,
      ...overrides,
    };
    for (const [k, v] of Object.entries(vals)) {
      if (v && v !== "" && !(k === "page" && v === 1)) params.set(k, String(v));
    }
    const qs = params.toString();
    router.replace(`/bets${qs ? `?${qs}` : ""}`);
  }

  function handleStatusChange(s: string) {
    setStatus(s);
    setPage(1);
    updateUrl({ status: s, page: 1 });
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Paper Bets</h1>
          <p className="text-sm text-muted-foreground">{data?.total ?? 0} total bets</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refetch()} disabled={isFetching}>
          {isFetching ? (
            <Loader2 size={14} className="mr-2 animate-spin" />
          ) : (
            <RefreshCw size={14} className="mr-2" />
          )}
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1">
          {STATUS_OPTIONS.map((s) => (
            <button
              key={s || "all"}
              onClick={() => handleStatusChange(s)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                status === s
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
              }`}
            >
              {s || "All"}
            </button>
          ))}
        </div>
        <Input
          placeholder="fixture_id"
          value={fixtureId}
          onChange={(e) => setFixtureId(e.target.value)}
          onBlur={() => {
            setPage(1);
            updateUrl({ fixture_id: fixtureId, page: 1 });
          }}
          className="w-72 font-mono text-xs"
        />
        <Input
          placeholder="venue"
          value={venue}
          onChange={(e) => setVenue(e.target.value)}
          onBlur={() => {
            setPage(1);
            updateUrl({ venue, page: 1 });
          }}
          className="w-24"
        />
        <Input
          type="date"
          value={dateFrom}
          onChange={(e) => {
            setDateFrom(e.target.value);
            setPage(1);
            updateUrl({ date_from: e.target.value, page: 1 });
          }}
          className="w-36 text-xs"
          title="From date"
        />
        <Input
          type="date"
          value={dateTo}
          onChange={(e) => {
            setDateTo(e.target.value);
            setPage(1);
            updateUrl({ date_to: e.target.value, page: 1 });
          }}
          className="w-36 text-xs"
          title="To date"
        />
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-muted-foreground" />
        </div>
      ) : (data?.bets ?? []).length === 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">No bets found.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50 text-left text-xs text-muted-foreground">
                <th className="px-3 py-2 font-medium">Fixture</th>
                <th className="px-3 py-2 font-medium">Market</th>
                <th className="px-3 py-2 font-medium">Sel.</th>
                <th className="px-3 py-2 font-medium">Odds</th>
                <th className="px-3 py-2 font-medium">Stake</th>
                <th className="px-3 py-2 font-medium">Edge</th>
                <th className="px-3 py-2 font-medium">Kelly f</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">CLV</th>
                <th className="px-3 py-2 font-medium">Age</th>
              </tr>
            </thead>
            <tbody>
              {data!.bets.map((b) => (
                <BetRow key={b.decision_id} bet={b} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {(data?.total ?? 0) > PAGE_SIZE && (
        <div className="flex items-center justify-end gap-2">
          <span className="text-xs text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => {
              setPage(page - 1);
              updateUrl({ page: page - 1 });
            }}
          >
            <ChevronLeft size={14} />
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => {
              setPage(page + 1);
              updateUrl({ page: page + 1 });
            }}
          >
            <ChevronRight size={14} />
          </Button>
        </div>
      )}
    </div>
  );
}

function BetRow({ bet: b }: { bet: BetResponse }) {
  const shortFixture =
    b.fixture_id.length > 36 ? b.fixture_id.slice(0, 33) + "…" : b.fixture_id;

  return (
    <tr className="border-b border-border/50 hover:bg-muted/30">
      <td className="px-3 py-2 font-mono text-xs">
        <Link
          href={`/bets/${encodeURIComponent(b.decision_id)}`}
          className="text-accent hover:underline"
          title={b.fixture_id}
        >
          {shortFixture}
        </Link>
      </td>
      <td className="px-3 py-2 text-xs">{b.market}</td>
      <td className="px-3 py-2 text-xs">
        <Badge variant="outline">{b.selection}</Badge>
      </td>
      <td className="px-3 py-2 font-mono text-xs">{b.odds_at_decision.toFixed(2)}</td>
      <td className="px-3 py-2 font-mono text-xs">£{b.stake_gbp}</td>
      <td className="px-3 py-2 font-mono text-xs">
        {(b.edge_pct * 100).toFixed(2)}%
      </td>
      <td className="px-3 py-2 font-mono text-xs">
        {(b.kelly_fraction_used * 100).toFixed(2)}%
      </td>
      <td className="px-3 py-2 text-xs">
        <SettlementBadge status={b.settlement_status} />
      </td>
      <td className={`px-3 py-2 font-mono text-xs font-medium ${clvColor(b.clv_pct)}`}>
        {formatClv(b.clv_pct)}
      </td>
      <td className="px-3 py-2 text-xs text-muted-foreground">
        {formatAge(b.decided_at)}
      </td>
    </tr>
  );
}

function SettlementBadge({ status }: { status: string }) {
  const variants: Record<string, string> = {
    won: "bg-green-500/15 text-green-600 dark:text-green-400",
    lost: "bg-red-500/15 text-red-600 dark:text-red-400",
    pending: "bg-yellow-500/15 text-yellow-600 dark:text-yellow-400",
    void: "bg-muted text-muted-foreground",
  };
  const cls = variants[status] ?? "bg-muted text-muted-foreground";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}
