"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useWarehouseTeam } from "@/lib/api/hooks";
import type { FormResult } from "@/lib/api/hooks";

function resultBadgeVariant(result: string | null): "default" | "destructive" | "secondary" {
  if (result === "W") return "default";
  if (result === "L") return "destructive";
  return "secondary";
}

function xgLabel(xg: string | null): string {
  if (xg === null) return "—";
  const n = parseFloat(xg);
  return isNaN(n) ? "—" : n.toFixed(2);
}

function FormRow({ row }: { row: FormResult }) {
  return (
    <tr className="hover:bg-muted/30">
      <td className="py-2 text-muted-foreground">{row.date ?? "—"}</td>
      <td className="py-2 font-mono text-xs">{row.opponent_id}</td>
      <td className="py-2 capitalize text-muted-foreground">{row.home_away}</td>
      <td className="py-2 tabular-nums">{row.score ?? "—"}</td>
      <td className="py-2">
        {row.result ? (
          <Badge variant={resultBadgeVariant(row.result)} className="w-7 justify-center text-xs">
            {row.result}
          </Badge>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="py-2 text-right tabular-nums text-muted-foreground">
        {xgLabel(row.home_xg)} / {xgLabel(row.away_xg)}
      </td>
    </tr>
  );
}

export default function TeamDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: team, isLoading, isError } = useWarehouseTeam(id);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/warehouse/teams">
          <Button variant="ghost" size="sm">
            <ArrowLeft size={14} />
            Teams
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold">
            {isLoading ? "Loading…" : (team?.name ?? id)}
          </h1>
          {team?.league && (
            <p className="text-sm text-muted-foreground">{team.league}</p>
          )}
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 size={14} className="animate-spin" />
          Loading team…
        </div>
      )}

      {isError && (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          Team not found or failed to load.
        </p>
      )}

      {team && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Last 5 Results</CardTitle>
          </CardHeader>
          <CardContent>
            {team.form.length === 0 ? (
              <p className="text-sm text-muted-foreground">No completed fixtures found.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="pb-2 text-left font-medium text-muted-foreground">Date</th>
                      <th className="pb-2 text-left font-medium text-muted-foreground">Opponent</th>
                      <th className="pb-2 text-left font-medium text-muted-foreground">Venue</th>
                      <th className="pb-2 text-left font-medium text-muted-foreground">Score</th>
                      <th className="pb-2 text-left font-medium text-muted-foreground">Result</th>
                      <th className="pb-2 text-right font-medium text-muted-foreground">xG (H/A)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {team.form.map((row) => (
                      <FormRow key={row.fixture_id} row={row} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
