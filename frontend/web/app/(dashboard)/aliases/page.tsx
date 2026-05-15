"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import {
  AlertTriangle,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  useAliases,
  useAliasConflicts,
  useRetireAlias,
} from "@/lib/api/hooks";
import type { AliasResponse } from "@/lib/api/hooks";
import { BootstrapModal } from "@/components/bootstrap/bootstrap-modal";

type StatusFilter = "all" | "active" | "retired";

export default function AliasesPage() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const statusParam = (searchParams.get("status") ?? "all") as StatusFilter;
  const [status, setStatus] = useState<StatusFilter>(statusParam);
  const [search, setSearch] = useState("");
  const [retireTarget, setRetireTarget] = useState<AliasResponse | null>(null);
  const [retireConfirm, setRetireConfirm] = useState("");
  const [showBootstrap, setShowBootstrap] = useState(false);

  const {
    data,
    isLoading,
    refetch,
    isFetching,
  } = useAliases({ status: status === "all" ? undefined : status });
  const { data: conflictsData } = useAliasConflicts();
  const retireMutation = useRetireAlias();

  const handleStatusChange = useCallback(
    (s: StatusFilter) => {
      setStatus(s);
      const params = new URLSearchParams(searchParams.toString());
      if (s === "all") params.delete("status");
      else params.set("status", s);
      router.replace(`/aliases?${params.toString()}`);
    },
    [searchParams, router],
  );

  const filteredAliases = (data?.aliases ?? []).filter((a) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      a.event_ticker.toLowerCase().includes(q) ||
      a.fixture_id.toLowerCase().includes(q)
    );
  });

  const conflictCount = conflictsData?.conflicts?.length ?? 0;

  function tickerSuffix(ticker: string): string {
    const parts = ticker.split("-");
    return parts.length > 1 ? parts[parts.length - 1] : ticker;
  }

  function handleRetireSubmit() {
    if (!retireTarget) return;
    const expected = `RETIRE-${tickerSuffix(retireTarget.event_ticker)}`;
    if (retireConfirm !== expected) {
      toast.error(`Type "${expected}" to confirm.`);
      return;
    }
    retireMutation.mutate(retireTarget.event_ticker, {
      onSuccess: () => {
        toast.success(`Retired alias ${retireTarget.event_ticker}`);
        setRetireTarget(null);
        setRetireConfirm("");
      },
      onError: (e) => toast.error(e.message),
    });
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Kalshi Event Aliases</h1>
          <p className="text-sm text-muted-foreground">
            {data?.total ?? 0} total aliases
            {conflictCount > 0 && (
              <span className="ml-2 text-yellow-500">
                ({conflictCount} conflict{conflictCount !== 1 ? "s" : ""})
              </span>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setShowBootstrap(true)}>
            <Zap size={14} className="mr-2" />
            Bootstrap
          </Button>
          <Link href="/aliases/create">
            <Button size="sm">
              <Plus size={14} className="mr-2" />
              New Alias
            </Button>
          </Link>
        </div>
      </div>

      {/* Conflicts banner */}
      {conflictCount > 0 && (
        <div className="flex items-start gap-3 rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-4">
          <AlertTriangle size={18} className="mt-0.5 text-yellow-500" />
          <div>
            <p className="text-sm font-medium text-yellow-500">
              {conflictCount} fixture{conflictCount !== 1 ? "s have" : " has"}{" "}
              multiple active aliases
            </p>
            <ul className="mt-1 list-inside list-disc text-xs text-muted-foreground">
              {conflictsData!.conflicts.slice(0, 5).map((c) => (
                <li key={c.fixture_id}>
                  <span className="font-mono">{c.fixture_id}</span> —{" "}
                  {c.alias_count} aliases ({c.tickers.join(", ")})
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1 rounded-md border border-border p-0.5">
          {(["all", "active", "retired"] as StatusFilter[]).map((s) => (
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

        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Filter by ticker or fixture…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={() => void refetch()}
          disabled={isFetching}
        >
          {isFetching ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <RefreshCw size={14} />
          )}
        </Button>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-muted-foreground" />
        </div>
      ) : filteredAliases.length === 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">
          No aliases found.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50 text-left text-muted-foreground">
                <th className="px-3 py-2 font-medium">Event Ticker</th>
                <th className="px-3 py-2 font-medium">Fixture ID</th>
                <th className="px-3 py-2 font-medium">Confidence</th>
                <th className="px-3 py-2 font-medium">Resolved By</th>
                <th className="px-3 py-2 font-medium">Resolved At</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredAliases.map((a) => (
                <tr
                  key={a.event_ticker}
                  className="border-b border-border/50 hover:bg-muted/30"
                >
                  <td className="px-3 py-2 font-mono text-xs">
                    <Link
                      href={`/kalshi/events/${a.event_ticker}`}
                      className="text-accent hover:underline"
                    >
                      {a.event_ticker}
                    </Link>
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{a.fixture_id}</td>
                  <td className="px-3 py-2 font-mono">
                    {(a.confidence * 100).toFixed(0)}%
                  </td>
                  <td className="px-3 py-2 text-xs">{a.resolved_by}</td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {a.resolved_at
                      ? new Date(a.resolved_at).toLocaleDateString()
                      : "—"}
                  </td>
                  <td className="px-3 py-2">
                    <Badge
                      variant={a.status === "active" ? "default" : "secondary"}
                    >
                      {a.status}
                    </Badge>
                  </td>
                  <td className="px-3 py-2">
                    {a.status === "active" && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setRetireTarget(a)}
                        className="h-7 text-xs text-destructive hover:text-destructive"
                      >
                        <Trash2 size={12} className="mr-1" />
                        Retire
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Retire confirmation modal */}
      {retireTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-lg">
            <h3 className="text-lg font-semibold">Retire Alias</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              This will retire the alias for{" "}
              <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
                {retireTarget.event_ticker}
              </code>
              . This action is append-only and cannot be undone.
            </p>
            <p className="mt-3 text-sm">
              Type{" "}
              <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
                RETIRE-{tickerSuffix(retireTarget.event_ticker)}
              </code>{" "}
              to confirm:
            </p>
            <Input
              className="mt-2 font-mono"
              placeholder={`RETIRE-${tickerSuffix(retireTarget.event_ticker)}`}
              value={retireConfirm}
              onChange={(e) => setRetireConfirm(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleRetireSubmit();
              }}
            />
            <div className="mt-4 flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setRetireTarget(null);
                  setRetireConfirm("");
                }}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={handleRetireSubmit}
                disabled={retireMutation.isPending}
              >
                {retireMutation.isPending && (
                  <Loader2 size={14} className="mr-2 animate-spin" />
                )}
                Retire
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Bootstrap modal */}
      {showBootstrap && (
        <BootstrapModal onClose={() => setShowBootstrap(false)} />
      )}
    </div>
  );
}
