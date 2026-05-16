"use client";

import { useState } from "react";
import Link from "next/link";
import { Database, Loader2, RefreshCw, Users, Zap, BarChart3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useWarehouseTables,
  useWarehouseQueryNames,
  useWarehouseQuery,
} from "@/lib/api/hooks";
import type { CannedQueryResponse } from "@/lib/api/hooks";

const DEFAULT_PARAMS = "{}";

function formatTimestamp(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function WarehousePage() {
  const { data: tables, isLoading: tablesLoading, refetch } = useWarehouseTables();
  const { data: queryNames } = useWarehouseQueryNames();
  const { mutate: runQuery, isPending: queryRunning } = useWarehouseQuery();

  const [selectedQuery, setSelectedQuery] = useState("");
  const [paramsText, setParamsText] = useState(DEFAULT_PARAMS);
  const [queryResult, setQueryResult] = useState<CannedQueryResponse | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);

  function handleRunQuery() {
    if (!selectedQuery) return;
    setQueryError(null);
    let params: Record<string, unknown> = {};
    try {
      params = JSON.parse(paramsText) as Record<string, unknown>;
    } catch {
      setQueryError("Invalid JSON in params field.");
      return;
    }
    runQuery(
      { query_name: selectedQuery, params },
      {
        onSuccess: (data) => setQueryResult(data),
        onError: (err) => setQueryError(err instanceof Error ? err.message : String(err)),
      },
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Warehouse</h1>
          <p className="text-sm text-muted-foreground">
            DuckDB tables, team data, and canned-query explorer
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refetch()} disabled={tablesLoading}>
          <RefreshCw size={14} className={tablesLoading ? "animate-spin" : ""} />
          Refresh
        </Button>
      </div>

      {/* Quick-nav cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {[
          { label: "Teams", href: "/warehouse/teams", icon: Users, desc: "Fixture history & form" },
          { label: "Snapshots", href: "/warehouse/snapshots", icon: BarChart3, desc: "Odds timeline browser" },
          { label: "Players", href: "/warehouse/players", icon: Database, desc: "Squad data (empty)" },
        ].map(({ label, href, icon: Icon, desc }) => (
          <Link key={href} href={href}>
            <Card className="cursor-pointer transition-colors hover:border-accent hover:bg-muted/50">
              <CardContent className="flex items-center gap-3 p-4">
                <Icon size={20} className="text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">{label}</p>
                  <p className="text-xs text-muted-foreground">{desc}</p>
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      {/* Tables overview */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Database size={16} />
            Tables
          </CardTitle>
        </CardHeader>
        <CardContent>
          {tablesLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 size={14} className="animate-spin" />
              Loading…
            </div>
          ) : !tables || tables.tables.length === 0 ? (
            <p className="text-sm text-muted-foreground">No tables found in warehouse.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="pb-2 text-left font-medium text-muted-foreground">Table</th>
                    <th className="pb-2 text-right font-medium text-muted-foreground">Rows</th>
                    <th className="pb-2 text-right font-medium text-muted-foreground">Last Write</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {tables.tables.map((t) => (
                    <tr key={t.name} className="hover:bg-muted/30">
                      <td className="py-2 font-mono text-xs">{t.name}</td>
                      <td className="py-2 text-right tabular-nums">{t.row_count.toLocaleString()}</td>
                      <td className="py-2 text-right text-muted-foreground">
                        {formatTimestamp(t.last_write)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Canned-query runner */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Zap size={16} />
            Query Runner
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">Query</label>
              <select
                className="rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
                value={selectedQuery}
                onChange={(e) => {
                  setSelectedQuery(e.target.value);
                  setQueryResult(null);
                  setQueryError(null);
                }}
              >
                <option value="">— select a query —</option>
                {(queryNames ?? []).map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">Params (JSON)</label>
              <input
                className="w-72 rounded-md border border-border bg-background px-3 py-1.5 font-mono text-sm focus:outline-none focus:ring-1 focus:ring-accent"
                value={paramsText}
                onChange={(e) => setParamsText(e.target.value)}
                placeholder='{"limit": 10}'
              />
            </div>
            <Button
              size="sm"
              onClick={handleRunQuery}
              disabled={!selectedQuery || queryRunning}
            >
              {queryRunning ? <Loader2 size={14} className="animate-spin" /> : null}
              Run
            </Button>
          </div>

          {queryError && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {queryError}
            </p>
          )}

          {queryResult && (
            <div className="overflow-x-auto">
              <p className="mb-2 text-xs text-muted-foreground">
                {queryResult.row_count} row{queryResult.row_count !== 1 ? "s" : ""}
              </p>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border">
                    {queryResult.columns.map((col) => (
                      <th key={col} className="pb-1 text-left font-medium text-muted-foreground">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {queryResult.rows.map((row, i) => (
                    <tr key={i} className="hover:bg-muted/30">
                      {row.map((cell, j) => (
                        <td key={j} className="py-1 pr-4 font-mono">
                          {cell === null ? <span className="text-muted-foreground">null</span> : String(cell)}
                        </td>
                      ))}
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
