"use client";

import { use, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useFixtureDetail } from "@/lib/api/hooks";
import type { FixtureDetailResponse } from "@/lib/api/hooks";
import SnapshotTimelineChart from "@/components/charts/SnapshotTimelineChart";

export default function FixtureDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const fixtureId = decodeURIComponent(id);
  const [activeTab, setActiveTab] = useState("overview");

  const { data, isLoading, error } = useFixtureDetail(fixtureId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 size={24} className="animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="space-y-4">
        <Link
          href="/fixtures"
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft size={14} />
          Fixtures
        </Link>
        <p className="text-sm text-destructive">Fixture not found.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Link
        href="/fixtures"
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft size={14} />
        Fixtures
      </Link>

      <FixtureHeader fixture={data} />

      <Tabs defaultValue="overview" onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="aliases">
            Aliases{" "}
            {data.alias_count > 0 && (
              <span className="ml-1.5 rounded-full bg-primary/10 px-1.5 text-xs text-primary">
                {data.alias_count}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="predictions">Predictions</TabsTrigger>
          <TabsTrigger value="bets">Bets</TabsTrigger>
          <TabsTrigger value="snapshots">Snapshots</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab fixture={data} />
        </TabsContent>

        <TabsContent value="aliases">
          <AliasesTab fixture={data} />
        </TabsContent>

        <TabsContent value="predictions">
          <PlaceholderTab
            message={`Predictions browser available in Stage 7. ${data.prediction_count} prediction${data.prediction_count !== 1 ? "s" : ""} for this fixture.`}
          />
        </TabsContent>

        <TabsContent value="bets">
          <PlaceholderTab
            message={`Bets browser available in Stage 8. ${data.bet_count} paper bet${data.bet_count !== 1 ? "s" : ""} for this fixture.`}
          />
        </TabsContent>

        <TabsContent value="snapshots">
          <SnapshotsTab fixtureId={fixtureId} active={activeTab === "snapshots"} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function FixtureHeader({ fixture: f }: { fixture: FixtureDetailResponse }) {
  const score =
    f.home_score_ft != null && f.away_score_ft != null
      ? `${f.home_score_ft} – ${f.away_score_ft}`
      : null;

  const kickoffStr = f.kickoff_utc
    ? new Date(f.kickoff_utc).toLocaleString("en-GB", {
        weekday: "short",
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZoneName: "short",
      })
    : "TBC";

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <Badge variant="outline">{f.league}</Badge>
        <Badge variant="outline">{f.season}</Badge>
        <Badge variant={f.status === "final" ? "secondary" : "default"}>
          {f.status}
        </Badge>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <div className="text-right">
          <p className="text-lg font-semibold">{f.home_team_id ?? f.home_team_raw ?? "—"}</p>
          <p className="text-xs text-muted-foreground">Home</p>
        </div>
        <div className="text-center">
          {score ? (
            <p className="text-3xl font-bold tabular-nums">{score}</p>
          ) : (
            <p className="text-muted-foreground">vs</p>
          )}
        </div>
        <div className="text-left">
          <p className="text-lg font-semibold">{f.away_team_id ?? f.away_team_raw ?? "—"}</p>
          <p className="text-xs text-muted-foreground">Away</p>
        </div>
      </div>

      <p className="text-sm text-muted-foreground">{kickoffStr}</p>
      <p className="font-mono text-xs text-muted-foreground">{f.fixture_id}</p>
    </div>
  );
}

function OverviewTab({ fixture: f }: { fixture: FixtureDetailResponse }) {
  const xgHome = f.home_xg ? parseFloat(f.home_xg).toFixed(2) : null;
  const xgAway = f.away_xg ? parseFloat(f.away_xg).toFixed(2) : null;

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <Card>
        <CardHeader>
          <CardTitle>Match Result</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          <Row label="Home" value={f.home_team_id ?? f.home_team_raw ?? "—"} />
          <Row label="Away" value={f.away_team_id ?? f.away_team_raw ?? "—"} />
          {f.home_score_ft != null && f.away_score_ft != null && (
            <Row label="Score" value={`${f.home_score_ft} – ${f.away_score_ft}`} />
          )}
          {f.result_ft && <Row label="Result" value={f.result_ft} />}
        </CardContent>
      </Card>

      {(xgHome || xgAway) && (
        <Card>
          <CardHeader>
            <CardTitle>xG (Understat)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            {xgHome && <Row label="Home xG" value={xgHome} />}
            {xgAway && <Row label="Away xG" value={xgAway} />}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Links</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          <Row label="Aliases" value={String(f.alias_count)} />
          <Row label="Predictions" value={String(f.prediction_count)} />
          <Row label="Paper bets" value={String(f.bet_count)} />
        </CardContent>
      </Card>
    </div>
  );
}

function AliasesTab({ fixture: f }: { fixture: FixtureDetailResponse }) {
  if (f.aliases.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No active Kalshi aliases for this fixture.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/50 text-left text-muted-foreground">
            <th className="px-3 py-2 font-medium">Event ticker</th>
            <th className="px-3 py-2 font-medium">Resolved by</th>
            <th className="px-3 py-2 font-medium">Confidence</th>
            <th className="px-3 py-2 font-medium">Resolved at</th>
          </tr>
        </thead>
        <tbody>
          {f.aliases.map((a) => (
            <tr key={a.event_ticker} className="border-b border-border/50 hover:bg-muted/30">
              <td className="px-3 py-2 font-mono text-xs">
                <Link
                  href={`/kalshi/events/${encodeURIComponent(a.event_ticker)}`}
                  className="text-accent hover:underline"
                >
                  {a.event_ticker}
                </Link>
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {a.resolved_by}
              </td>
              <td className="px-3 py-2 text-xs">
                {(a.confidence * 100).toFixed(0)}%
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {a.resolved_at
                  ? new Date(a.resolved_at).toLocaleDateString("en-GB")
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PlaceholderTab({ message }: { message: string }) {
  return (
    <Card>
      <CardContent className="py-12 text-center text-sm text-muted-foreground">
        {message}
      </CardContent>
    </Card>
  );
}

function SnapshotsTab({
  fixtureId,
  active,
}: {
  fixtureId: string;
  active: boolean;
}) {
  // Snapshots are loaded from the warehouse odds_snapshots table via the
  // warehouse adapter (Stage 10). For now show an empty chart state.
  void fixtureId;
  void active;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Odds Snapshots Timeline</CardTitle>
      </CardHeader>
      <CardContent>
        <SnapshotTimelineChart snapshots={[]} />
      </CardContent>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}
