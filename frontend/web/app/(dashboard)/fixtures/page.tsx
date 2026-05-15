"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import {
  ChevronLeft,
  ChevronRight,
  Loader2,
  RefreshCw,
  Search,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useFixtures } from "@/lib/api/hooks";
import type { FixtureResponse } from "@/lib/api/hooks";

type StatusFilter = "all" | "final" | "scheduled";
const PAGE_SIZES = [25, 50, 100] as const;

export default function FixturesPage() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const statusParam = (searchParams.get("status") ?? "all") as StatusFilter;
  const leagueParam = searchParams.get("league") ?? "";
  const seasonParam = searchParams.get("season") ?? "";
  const fromParam = searchParams.get("from") ?? "";
  const toParam = searchParams.get("to") ?? "";
  const pageParam = parseInt(searchParams.get("page") ?? "1", 10);
  const pageSizeParam = parseInt(
    searchParams.get("pageSize") ?? "50",
    10,
  ) as (typeof PAGE_SIZES)[number];

  const [status, setStatus] = useState<StatusFilter>(statusParam);
  const [league, setLeague] = useState(leagueParam);
  const [season, setSeason] = useState(seasonParam);
  const [dateFrom, setDateFrom] = useState(fromParam);
  const [dateTo, setDateTo] = useState(toParam);
  const [page, setPage] = useState(pageParam);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZES)[number]>(pageSizeParam);
  const [search, setSearch] = useState("");

  const offset = (page - 1) * pageSize;

  const { data, isLoading, refetch, isFetching } = useFixtures({
    status: status === "all" ? undefined : status,
    league: league || undefined,
    season: season || undefined,
    from: dateFrom || undefined,
    to: dateTo || undefined,
    limit: pageSize,
    offset,
  });

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / pageSize));

  const updateUrl = useCallback(
    (overrides: Record<string, string | number>) => {
      const params = new URLSearchParams();
      const vals: Record<string, string | number> = {
        status,
        league,
        season,
        from: dateFrom,
        to: dateTo,
        page,
        pageSize,
        ...overrides,
      };
      for (const [k, v] of Object.entries(vals)) {
        if (v && v !== "all" && v !== "" && !(k === "page" && v === 1) && !(k === "pageSize" && v === 50)) {
          params.set(k, String(v));
        }
      }
      const qs = params.toString();
      router.replace(`/fixtures${qs ? `?${qs}` : ""}`);
    },
    [status, league, season, dateFrom, dateTo, page, pageSize, router],
  );

  function handleStatusChange(s: StatusFilter) {
    setStatus(s);
    setPage(1);
    updateUrl({ status: s, page: 1 });
  }

  function handlePageSizeChange(size: (typeof PAGE_SIZES)[number]) {
    setPageSize(size);
    setPage(1);
    updateUrl({ pageSize: size, page: 1 });
  }

  function handlePageChange(p: number) {
    setPage(p);
    updateUrl({ page: p });
  }

  const filteredFixtures = (data?.fixtures ?? []).filter((f) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      f.fixture_id.toLowerCase().includes(q) ||
      (f.home_team_id?.toLowerCase().includes(q) ?? false) ||
      (f.away_team_id?.toLowerCase().includes(q) ?? false) ||
      (f.home_team_raw?.toLowerCase().includes(q) ?? false) ||
      (f.away_team_raw?.toLowerCase().includes(q) ?? false)
    );
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Fixtures</h1>
          <p className="text-sm text-muted-foreground">
            {data?.total ?? 0} total fixtures
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => void refetch()}
          disabled={isFetching}
        >
          {isFetching ? (
            <Loader2 size={14} className="mr-2 animate-spin" />
          ) : (
            <RefreshCw size={14} className="mr-2" />
          )}
          Refresh
        </Button>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Status toggle */}
        <div className="flex gap-1 rounded-md border border-border p-0.5">
          {(["all", "final", "scheduled"] as StatusFilter[]).map((s) => (
            <button
              key={s}
              onClick={() => handleStatusChange(s)}
              className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
                status === s
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>

        {/* League filter */}
        <Input
          placeholder="League"
          value={league}
          onChange={(e) => {
            setLeague(e.target.value);
            setPage(1);
          }}
          onBlur={() => updateUrl({ league, page: 1 })}
          className="w-24"
        />

        {/* Season filter */}
        <Input
          placeholder="Season"
          value={season}
          onChange={(e) => {
            setSeason(e.target.value);
            setPage(1);
          }}
          onBlur={() => updateUrl({ season, page: 1 })}
          className="w-28"
        />

        {/* Date range */}
        <Input
          type="date"
          value={dateFrom}
          onChange={(e) => {
            setDateFrom(e.target.value);
            setPage(1);
          }}
          onBlur={() => updateUrl({ from: dateFrom, page: 1 })}
          className="w-36"
        />
        <span className="text-xs text-muted-foreground">to</span>
        <Input
          type="date"
          value={dateTo}
          onChange={(e) => {
            setDateTo(e.target.value);
            setPage(1);
          }}
          onBlur={() => updateUrl({ to: dateTo, page: 1 })}
          className="w-36"
        />

        {/* Text search */}
        <div className="relative flex-1">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            placeholder="Filter by team or fixture…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-muted-foreground" />
        </div>
      ) : filteredFixtures.length === 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">
          No fixtures found.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50 text-left text-muted-foreground">
                <th className="px-3 py-2 font-medium">Fixture ID</th>
                <th className="px-3 py-2 font-medium">League</th>
                <th className="px-3 py-2 font-medium">Kickoff</th>
                <th className="px-3 py-2 font-medium">Home</th>
                <th className="px-3 py-2 font-medium">Away</th>
                <th className="px-3 py-2 font-medium">Score</th>
                <th className="px-3 py-2 font-medium">Aliases</th>
                <th className="px-3 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredFixtures.map((f) => (
                <FixtureRow key={f.fixture_id} fixture={f} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {(data?.total ?? 0) > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>Rows per page:</span>
            {PAGE_SIZES.map((size) => (
              <button
                key={size}
                onClick={() => handlePageSizeChange(size as (typeof PAGE_SIZES)[number])}
                className={`rounded px-2 py-0.5 ${
                  pageSize === size
                    ? "bg-accent text-accent-foreground"
                    : "hover:text-foreground"
                }`}
              >
                {size}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => handlePageChange(page - 1)}
            >
              <ChevronLeft size={14} />
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => handlePageChange(page + 1)}
            >
              <ChevronRight size={14} />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function FixtureRow({ fixture: f }: { fixture: FixtureResponse }) {
  const score =
    f.home_score_ft != null && f.away_score_ft != null
      ? `${f.home_score_ft}–${f.away_score_ft}`
      : "—";

  const kickoffStr = f.kickoff_utc
    ? new Date(f.kickoff_utc).toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })
    : "—";

  const kickoffLocal = f.kickoff_utc
    ? new Date(f.kickoff_utc).toLocaleString()
    : "";

  return (
    <tr className="border-b border-border/50 hover:bg-muted/30">
      <td className="px-3 py-2 font-mono text-xs">
        <Link
          href={`/fixtures/${encodeURIComponent(f.fixture_id)}`}
          className="text-accent hover:underline"
        >
          {f.fixture_id.length > 40
            ? f.fixture_id.slice(0, 37) + "…"
            : f.fixture_id}
        </Link>
      </td>
      <td className="px-3 py-2 text-xs">{f.league}</td>
      <td className="px-3 py-2 text-xs" title={kickoffLocal}>
        {kickoffStr}
      </td>
      <td className="px-3 py-2 text-xs">
        {f.home_team_id ?? f.home_team_raw ?? "—"}
      </td>
      <td className="px-3 py-2 text-xs">
        {f.away_team_id ?? f.away_team_raw ?? "—"}
      </td>
      <td className="px-3 py-2 font-mono text-xs">{score}</td>
      <td className="px-3 py-2 text-xs">
        {f.alias_count > 0 ? (
          <Badge variant="default">{f.alias_count}</Badge>
        ) : (
          <span className="text-muted-foreground">0</span>
        )}
      </td>
      <td className="px-3 py-2">
        <Badge variant={f.status === "final" ? "secondary" : "default"}>
          {f.status}
        </Badge>
      </td>
    </tr>
  );
}
