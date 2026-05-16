"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, RefreshCw, Loader2, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useDiagnosticsLogs } from "@/lib/api/hooks";
import type { LogEntry } from "@/lib/api/hooks";

const LEVELS = ["ALL", "DEBUG", "INFO", "WARNING", "ERROR"];
const LIMITS = [50, 100, 200, 500];

const LEVEL_BADGE: Record<string, string> = {
  DEBUG: "secondary",
  INFO: "outline",
  WARNING: "default",
  ERROR: "destructive",
};

function LogRow({ entry }: { entry: LogEntry }) {
  const variant =
    (LEVEL_BADGE[entry.level] as
      | "default"
      | "secondary"
      | "destructive"
      | "outline"
      | undefined) ?? "outline";

  const ts = (() => {
    try {
      return new Date(entry.timestamp).toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return entry.timestamp;
    }
  })();

  return (
    <tr className="border-b last:border-0 hover:bg-muted/30">
      <td className="py-1.5 pr-3 font-mono text-xs text-muted-foreground whitespace-nowrap">
        {ts}
      </td>
      <td className="py-1.5 pr-3">
        <Badge variant={variant} className="text-xs">
          {entry.level}
        </Badge>
      </td>
      <td className="py-1.5 pr-3 font-mono text-xs text-muted-foreground whitespace-nowrap max-w-[140px] truncate">
        {entry.logger}
      </td>
      <td className="py-1.5 font-mono text-xs break-all">{entry.message}</td>
    </tr>
  );
}

export default function DiagnosticsLogsPage() {
  const [level, setLevel] = useState("ALL");
  const [limit, setLimit] = useState(100);
  const [search, setSearch] = useState("");

  const { data, isLoading, refetch, isFetching } = useDiagnosticsLogs({
    level: level === "ALL" ? undefined : level,
    limit,
  });

  const entries = data?.entries ?? [];
  const filtered = search.trim()
    ? entries.filter(
        (e) =>
          e.message.toLowerCase().includes(search.toLowerCase()) ||
          e.logger.toLowerCase().includes(search.toLowerCase()),
      )
    : entries;

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center gap-3">
        <Link href="/diagnostics">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="mr-1 h-4 w-4" />
            Diagnostics
          </Button>
        </Link>
        <h1 className="text-2xl font-bold">Logs</h1>
        <span className="ml-auto text-sm text-muted-foreground">
          {data ? `${filtered.length} / ${data.total} entries` : ""}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <select
          className="h-9 rounded-md border bg-background px-3 text-sm"
          value={level}
          onChange={(e) => setLevel(e.target.value)}
        >
          {LEVELS.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>

        <select
          className="h-9 rounded-md border bg-background px-3 text-sm"
          value={String(limit)}
          onChange={(e) => setLimit(Number(e.target.value))}
        >
          {LIMITS.map((n) => (
            <option key={n} value={String(n)}>
              Last {n}
            </option>
          ))}
        </select>

        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-8"
            placeholder="Filter messages…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={() => void refetch()}
          disabled={isFetching}
        >
          <RefreshCw className={`mr-2 h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Log Buffer</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center gap-2 text-muted-foreground py-8 justify-center">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : filtered.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No log entries match the current filter.
            </p>
          ) : (
            <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-card">
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-1 font-medium pr-3">Time</th>
                    <th className="pb-1 font-medium pr-3">Level</th>
                    <th className="pb-1 font-medium pr-3">Logger</th>
                    <th className="pb-1 font-medium">Message</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((entry, i) => (
                    <LogRow key={i} entry={entry} />
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
