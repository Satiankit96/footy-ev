"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useBetDetail } from "@/lib/api/hooks";
import type { BetDetailResponse, KellyBreakdown, EdgeMath } from "@/lib/api/hooks";

function clvColor(clv: number | null): string {
  if (clv === null) return "text-muted-foreground";
  return clv >= 0 ? "text-green-500" : "text-red-500";
}

export default function BetDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const decisionId = decodeURIComponent(id);
  const { data, isLoading, error } = useBetDetail(decisionId);

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
        <BackLink />
        <p className="text-sm text-destructive">Bet not found.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <BackLink />
      <BetHeader bet={data} />

      <div className="grid gap-4 lg:grid-cols-2">
        <EdgeMathCard math={data.edge_math} />
        <KellyCard kb={data.kelly_breakdown} stakeGbp={data.stake_gbp} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <OddsCard bet={data} />
        <SettlementCard bet={data} />
      </div>

      <ClvCard bet={data} />

      <MetaCard bet={data} />
    </div>
  );
}

function BackLink() {
  return (
    <Link
      href="/bets"
      className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft size={14} />
      Paper Bets
    </Link>
  );
}

function BetHeader({ bet: b }: { bet: BetDetailResponse }) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{b.market}</Badge>
        <Badge variant="secondary">{b.selection}</Badge>
        <span className="text-xs text-muted-foreground">{b.venue}</span>
      </div>
      <Link
        href={`/fixtures/${encodeURIComponent(b.fixture_id)}`}
        className="font-mono text-xs text-accent hover:underline"
      >
        {b.fixture_id}
      </Link>
      <div className="flex items-center gap-4">
        <SettlementBadge status={b.settlement_status} />
        {b.decided_at && (
          <span className="text-xs text-muted-foreground">
            Decided {new Date(b.decided_at).toLocaleString("en-GB")}
          </span>
        )}
      </div>
    </div>
  );
}

function EdgeMathCard({ math: m }: { math: EdgeMath }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Edge Math</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 text-sm">
        <p className="mb-2 font-mono text-xs text-muted-foreground">
          edge = p_calibrated × odds − 1 − commission
        </p>
        <Row label="p_calibrated" value={m.p_calibrated.toFixed(4)} mono />
        <Row label="odds (decimal)" value={m.odds_decimal.toFixed(3)} mono />
        <Row label="commission" value={m.commission.toFixed(4)} mono />
        <div className="my-2 border-t border-border" />
        <Row
          label="edge"
          value={`${(m.edge * 100).toFixed(2)}%`}
          mono
          highlight
        />
      </CardContent>
    </Card>
  );
}

function KellyCard({
  kb,
  stakeGbp,
}: {
  kb: KellyBreakdown;
  stakeGbp: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Kelly Breakdown</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 text-sm">
        <p className="mb-2 font-mono text-xs text-muted-foreground">
          p_lb = p_hat − k·σ; f_full = (b·p_lb − q)/b; f_used = base × clv_mul × f_full
        </p>
        <Row label="p_hat" value={kb.p_hat.toFixed(4)} mono />
        <Row label="σ_p" value={kb.sigma_p.toFixed(4)} mono />
        <Row label="k (uncertainty)" value={kb.uncertainty_k.toFixed(1)} mono />
        <Row label="p_lb" value={kb.p_lb.toFixed(4)} mono highlight />
        <Row label="b (odds − 1)" value={kb.b.toFixed(4)} mono />
        <Row label="q (1 − p_lb)" value={kb.q.toFixed(4)} mono />
        <Row label="f_full" value={(kb.f_full * 100).toFixed(3) + "%"} mono highlight />
        <div className="my-2 border-t border-border" />
        <Row label="base_fraction" value={(kb.base_fraction * 100).toFixed(0) + "%"} mono />
        <Row label="per_bet_cap" value={(kb.per_bet_cap_pct * 100).toFixed(0) + "%"} mono />
        <Row
          label="f_used"
          value={
            (kb.f_used * 100).toFixed(3) +
            "%" +
            (kb.per_bet_cap_hit ? " (capped)" : "")
          }
          mono
          highlight
        />
        <Row label="bankroll" value={`£${kb.bankroll_used}`} mono />
        <div className="my-2 border-t border-border" />
        <Row label="stake" value={`£${stakeGbp}`} mono highlight />
      </CardContent>
    </Card>
  );
}

function OddsCard({ bet: b }: { bet: BetDetailResponse }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Odds</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 text-sm">
        <Row label="Quoted (at decision)" value={b.odds_at_decision.toFixed(3)} mono />
        <Row label="Venue" value={b.venue} />
        {b.closing_odds != null && (
          <>
            <Row label="Closing odds" value={b.closing_odds.toFixed(3)} mono />
          </>
        )}
      </CardContent>
    </Card>
  );
}

function SettlementCard({ bet: b }: { bet: BetDetailResponse }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Settlement</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">Status</span>
          <SettlementBadge status={b.settlement_status} />
        </div>
        {b.pnl_gbp != null && (
          <Row
            label="P&L"
            value={`£${b.pnl_gbp}`}
            mono
            highlight
          />
        )}
        <div className="space-y-1 text-xs text-muted-foreground">
          <TimelineRow label="Decided" ts={b.decided_at} />
          {b.settled_at && <TimelineRow label="Settled" ts={b.settled_at} />}
        </div>
      </CardContent>
    </Card>
  );
}

function ClvCard({ bet: b }: { bet: BetDetailResponse }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Closing-Line Value (CLV)</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 text-sm">
        {b.clv_pct != null ? (
          <>
            <div className="flex items-center justify-between gap-4">
              <span className="text-muted-foreground">CLV %</span>
              <span
                className={`font-mono text-lg font-bold ${clvColor(b.clv_pct)}`}
              >
                {b.clv_pct >= 0 ? "+" : ""}
                {(b.clv_pct * 100).toFixed(2)}%
              </span>
            </div>
            {b.closing_odds && (
              <p className="font-mono text-xs text-muted-foreground">
                formula: {b.odds_at_decision.toFixed(3)} / {b.closing_odds.toFixed(3)} − 1
              </p>
            )}
          </>
        ) : (
          <p className="text-muted-foreground">
            CLV not yet backfilled — run &quot;Backfill CLV&quot; from the{" "}
            <Link href="/clv" className="text-accent hover:underline">
              CLV analytics
            </Link>{" "}
            page after settlement.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function MetaCard({ bet: b }: { bet: BetDetailResponse }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Metadata</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 text-sm">
        <Row label="Decision ID" value={<span className="font-mono text-xs">{b.decision_id}</span>} />
        <Row label="Features hash" value={<span className="font-mono text-xs">{b.features_hash}</span>} />
        {b.run_id && (
          <Row label="Run ID" value={<span className="font-mono text-xs">{b.run_id}</span>} />
        )}
        {b.stake_gbp && (
          <Row
            label="Prediction"
            value={
              <Link
                href={`/predictions?fixture_id=${encodeURIComponent(b.fixture_id)}`}
                className="text-xs text-accent hover:underline"
              >
                View predictions for fixture
              </Link>
            }
          />
        )}
      </CardContent>
    </Card>
  );
}

function Row({
  label,
  value,
  mono = false,
  highlight = false,
}: {
  label: string;
  value: string | React.ReactNode;
  mono?: boolean;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className={`${highlight ? "font-semibold" : "font-medium"} ${mono ? "font-mono" : ""}`}>
        {value}
      </span>
    </div>
  );
}

function TimelineRow({ label, ts }: { label: string; ts: string | null }) {
  if (!ts) return null;
  return (
    <div className="flex items-center gap-2">
      <span className="w-16 shrink-0">{label}:</span>
      <span className="font-mono">{new Date(ts).toLocaleString("en-GB")}</span>
    </div>
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
