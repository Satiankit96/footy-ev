"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2 } from "lucide-react";
import { useKalshiMarketDetail } from "@/lib/api/hooks";

export default function MarketDetailPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = use(params);
  const { data, isLoading } = useKalshiMarketDetail(ticker);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={24} className="animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="py-20 text-center text-sm text-muted-foreground">
        Market not found.
      </div>
    );
  }

  const { market: m, recent_snapshots } = data;
  const spread =
    m.yes_ask && m.yes_bid
      ? (parseFloat(m.yes_ask) - parseFloat(m.yes_bid)).toFixed(4)
      : null;

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        href={`/kalshi/events/${m.event_ticker}`}
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft size={14} />
        Back to event
      </Link>

      {/* Market header */}
      <div className="rounded-lg border border-border bg-card p-4">
        <p className="font-mono text-xs text-muted-foreground">
          <Link
            href={`/kalshi/events/${m.event_ticker}`}
            className="text-accent hover:underline"
          >
            {m.event_ticker}
          </Link>
        </p>
        <h2 className="font-mono text-lg font-semibold">{m.ticker}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Floor Strike: <span className="font-mono">{m.floor_strike}</span>
        </p>
      </div>

      {/* Price card */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <PriceCell label="YES Bid" value={m.yes_bid} size={m.yes_bid_size} />
        <PriceCell label="YES Ask" value={m.yes_ask} size={m.yes_ask_size} />
        <PriceCell label="NO Bid" value={m.no_bid} />
        <PriceCell label="NO Ask" value={m.no_ask} />
      </div>

      {/* Computed values */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <ComputedCard
          label="Decimal Odds"
          value={m.decimal_odds ?? "—"}
          sub="1 / YES bid"
        />
        <ComputedCard
          label="Implied Probability"
          value={
            m.implied_probability ? `${m.implied_probability}%` : "—"
          }
          sub="YES bid as %"
        />
        <ComputedCard
          label="Spread"
          value={spread ?? "—"}
          sub="YES ask − YES bid"
        />
      </div>

      {/* Snapshots */}
      <div className="rounded-lg border border-border bg-card p-4">
        <h3 className="mb-3 text-sm font-semibold">
          Recent Snapshots (24h)
        </h3>
        {recent_snapshots.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No historical snapshots for this market yet. Run a pipeline cycle to
            capture.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="pb-2 pr-4 font-medium">Timestamp</th>
                  <th className="pb-2 pr-4 font-medium">YES Bid</th>
                  <th className="pb-2 font-medium">NO Bid</th>
                </tr>
              </thead>
              <tbody>
                {recent_snapshots.map((snap, i) => (
                  <tr key={i} className="border-b border-border/50">
                    <td className="py-1 pr-4 font-mono text-xs">
                      {String(
                        snap.snapshot_ts ??
                          snap.timestamp ??
                          snap.captured_at ??
                          "—",
                      )}
                    </td>
                    <td className="py-1 pr-4 font-mono text-xs">
                      {String(snap.yes_bid_dollars ?? snap.yes_bid ?? "—")}
                    </td>
                    <td className="py-1 font-mono text-xs">
                      {String(snap.no_bid_dollars ?? snap.no_bid ?? "—")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function PriceCell({
  label,
  value,
  size,
}: {
  label: string;
  value: string | null;
  size?: number | null;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 text-center">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 font-mono text-2xl font-bold">
        {value ?? "—"}
      </p>
      {size != null && (
        <p className="mt-1 text-xs text-muted-foreground">
          size: {size}
        </p>
      )}
    </div>
  );
}

function ComputedCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 font-mono text-xl font-semibold">{value}</p>
      <p className="mt-1 text-xs text-muted-foreground">{sub}</p>
    </div>
  );
}
