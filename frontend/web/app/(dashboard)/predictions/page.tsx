"use client";

import { useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, Loader2, Play, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { usePredictions, useRunPredictions } from "@/lib/api/hooks";
import type { PredictionResponse } from "@/lib/api/hooks";

const PAGE_SIZE = 50;

function formatAge(isoStr: string | null): string {
  if (!isoStr) return "—";
  const diffMs = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function PredictionsPage() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [fixtureId, setFixtureId] = useState(searchParams.get("fixture_id") ?? "");
  const [modelVersion, setModelVersion] = useState(searchParams.get("model_version") ?? "");
  const [market, setMarket] = useState(searchParams.get("market") ?? "");
  const [page, setPage] = useState(parseInt(searchParams.get("page") ?? "1", 10));

  const offset = (page - 1) * PAGE_SIZE;

  const { data, isLoading, isFetching, refetch } = usePredictions({
    fixture_id: fixtureId || undefined,
    model_version: modelVersion || undefined,
    market: market || undefined,
    limit: PAGE_SIZE,
    offset,
  });

  const runMutation = useRunPredictions();
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));

  function updateUrl(overrides: Record<string, string | number>) {
    const params = new URLSearchParams();
    const vals: Record<string, string | number> = {
      fixture_id: fixtureId,
      model_version: modelVersion,
      market,
      page,
      ...overrides,
    };
    for (const [k, v] of Object.entries(vals)) {
      if (v && v !== "" && !(k === "page" && v === 1)) params.set(k, String(v));
    }
    const qs = params.toString();
    router.replace(`/predictions${qs ? `?${qs}` : ""}`);
  }

  function handleRun() {
    runMutation.mutate(undefined, {
      onSuccess: (res) => {
        toast.success(`Prediction job started — job_id: ${res.job_id}`);
        void refetch();
      },
      onError: (err) => {
        toast.error(err instanceof Error ? err.message : "Failed to start prediction run");
      },
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Predictions</h1>
          <p className="text-sm text-muted-foreground">{data?.total ?? 0} total predictions</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => void refetch()} disabled={isFetching}>
            {isFetching ? (
              <Loader2 size={14} className="mr-2 animate-spin" />
            ) : (
              <RefreshCw size={14} className="mr-2" />
            )}
            Refresh
          </Button>
          <Button size="sm" onClick={handleRun} disabled={runMutation.isPending}>
            {runMutation.isPending ? (
              <Loader2 size={14} className="mr-2 animate-spin" />
            ) : (
              <Play size={14} className="mr-2" />
            )}
            Run predictions
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
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
          placeholder="model_version"
          value={modelVersion}
          onChange={(e) => setModelVersion(e.target.value)}
          onBlur={() => {
            setPage(1);
            updateUrl({ model_version: modelVersion, page: 1 });
          }}
          className="w-36"
        />
        <Input
          placeholder="market"
          value={market}
          onChange={(e) => setMarket(e.target.value)}
          onBlur={() => {
            setPage(1);
            updateUrl({ market, page: 1 });
          }}
          className="w-28"
        />
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-muted-foreground" />
        </div>
      ) : (data?.predictions ?? []).length === 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">No predictions found.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50 text-left text-xs text-muted-foreground">
                <th className="px-3 py-2 font-medium">Fixture</th>
                <th className="px-3 py-2 font-medium">Market</th>
                <th className="px-3 py-2 font-medium">Sel.</th>
                <th className="px-3 py-2 font-medium">p_raw</th>
                <th className="px-3 py-2 font-medium">p_cal.</th>
                <th className="px-3 py-2 font-medium">σ_p</th>
                <th className="px-3 py-2 font-medium">Model</th>
                <th className="px-3 py-2 font-medium">Age</th>
              </tr>
            </thead>
            <tbody>
              {data!.predictions.map((p) => (
                <PredictionRow key={p.prediction_id} prediction={p} />
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

function PredictionRow({ prediction: p }: { prediction: PredictionResponse }) {
  const shortFixture =
    p.fixture_id.length > 36 ? p.fixture_id.slice(0, 33) + "…" : p.fixture_id;
  return (
    <tr className="border-b border-border/50 hover:bg-muted/30">
      <td className="px-3 py-2 font-mono text-xs">
        <Link
          href={`/predictions/${encodeURIComponent(p.prediction_id)}`}
          className="text-accent hover:underline"
          title={p.fixture_id}
        >
          {shortFixture}
        </Link>
      </td>
      <td className="px-3 py-2 text-xs">{p.market}</td>
      <td className="px-3 py-2 text-xs">
        <Badge variant="outline">{p.selection}</Badge>
      </td>
      <td className="px-3 py-2 font-mono text-xs">{p.p_raw.toFixed(4)}</td>
      <td className="px-3 py-2 font-mono text-xs">{p.p_calibrated.toFixed(4)}</td>
      <td className="px-3 py-2 font-mono text-xs">
        {p.sigma_p != null ? p.sigma_p.toFixed(4) : "—"}
      </td>
      <td className="px-3 py-2 text-xs text-muted-foreground">{p.model_version}</td>
      <td className="px-3 py-2 text-xs text-muted-foreground">{formatAge(p.as_of)}</td>
    </tr>
  );
}
