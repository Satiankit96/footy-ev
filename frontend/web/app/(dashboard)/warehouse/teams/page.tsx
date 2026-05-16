"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useWarehouseTeams } from "@/lib/api/hooks";
import type { TeamRow } from "@/lib/api/hooks";

function resultBadge(result: string | null): string {
  if (result === "W") return "text-green-500";
  if (result === "L") return "text-red-500";
  return "text-muted-foreground";
}

export default function TeamsPage() {
  const [leagueFilter, setLeagueFilter] = useState("");
  const { data, isLoading } = useWarehouseTeams(leagueFilter || undefined);

  const teams: TeamRow[] = data?.teams ?? [];

  // Collect unique leagues for filter suggestions
  const allLeagues = Array.from(
    new Set(teams.map((t) => t.league).filter(Boolean)),
  ) as string[];

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
          <h1 className="text-2xl font-bold">Teams</h1>
          <p className="text-sm text-muted-foreground">
            Teams derived from fixture history
          </p>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Users size={16} />
              {data ? `${data.total} teams` : "Teams"}
            </CardTitle>
            <div className="flex items-center gap-2">
              <Input
                placeholder="Filter by league…"
                value={leagueFilter}
                onChange={(e) => setLeagueFilter(e.target.value)}
                className="h-8 w-48 text-sm"
              />
              {leagueFilter && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setLeagueFilter("")}
                  className="h-8 text-xs"
                >
                  Clear
                </Button>
              )}
            </div>
          </div>
          {allLeagues.length > 0 && (
            <div className="flex flex-wrap gap-1 pt-1">
              {allLeagues.map((lg) => (
                <button
                  key={lg}
                  onClick={() => setLeagueFilter(lg)}
                  className={`rounded-full px-2 py-0.5 text-xs transition-colors ${
                    leagueFilter === lg
                      ? "bg-accent text-accent-foreground"
                      : "bg-muted text-muted-foreground hover:bg-muted/80"
                  }`}
                >
                  {lg}
                </button>
              ))}
            </div>
          )}
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 size={14} className="animate-spin" />
              Loading…
            </div>
          ) : teams.length === 0 ? (
            <p className="text-sm text-muted-foreground">No teams found.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="pb-2 text-left font-medium text-muted-foreground">Team ID</th>
                    <th className="pb-2 text-left font-medium text-muted-foreground">Name</th>
                    <th className="pb-2 text-left font-medium text-muted-foreground">League</th>
                    <th className="pb-2 text-right font-medium text-muted-foreground">Fixtures</th>
                    <th className="pb-2"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {teams.map((team) => (
                    <tr key={team.team_id} className="hover:bg-muted/30">
                      <td className="py-2 font-mono text-xs">{team.team_id}</td>
                      <td className="py-2">{team.name ?? <span className="text-muted-foreground">—</span>}</td>
                      <td className="py-2 text-muted-foreground">{team.league ?? "—"}</td>
                      <td className="py-2 text-right tabular-nums">{team.fixture_count}</td>
                      <td className="py-2 text-right">
                        <Link
                          href={`/warehouse/teams/${team.team_id}`}
                          className="text-xs text-accent hover:underline"
                        >
                          Detail →
                        </Link>
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
