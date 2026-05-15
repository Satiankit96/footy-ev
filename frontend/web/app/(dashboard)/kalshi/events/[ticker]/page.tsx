"use client";

import { use, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ExternalLink, LinkIcon, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useKalshiEventDetail } from "@/lib/api/hooks";
import type { KalshiMarketResponse } from "@/lib/api/hooks";
import { BootstrapModal } from "@/components/bootstrap/bootstrap-modal";

const OU25_STRIKE = "2.5";

export default function EventDetailPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = use(params);
  const { data, isLoading } = useKalshiEventDetail(ticker);

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
        Event not found.
      </div>
    );
  }

  const { event, markets } = data;

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        href="/kalshi"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft size={14} />
        Back to Kalshi
      </Link>

      {/* Event header */}
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="font-mono text-xs text-muted-foreground">
              {event.series_ticker}
            </p>
            <h2 className="text-lg font-semibold">{event.title}</h2>
            {event.sub_title && (
              <p className="text-sm text-muted-foreground">{event.sub_title}</p>
            )}
            {event.category && (
              <p className="mt-1 text-xs text-muted-foreground">
                Category: {event.category}
              </p>
            )}
            <p className="mt-1 font-mono text-xs text-muted-foreground">
              {event.event_ticker}
            </p>
          </div>
          <div>
            <AliasCard
              status={event.alias_status}
              fixtureId={event.fixture_id}
            />
          </div>
        </div>
      </div>

      {/* Markets table */}
      <div className="rounded-lg border border-border bg-card p-4">
        <h3 className="mb-3 text-sm font-semibold">
          Markets ({markets.length})
        </h3>
        {markets.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No markets found for this event.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="pb-2 pr-4 font-medium">Ticker</th>
                  <th className="pb-2 pr-4 font-medium">Floor Strike</th>
                  <th className="pb-2 pr-4 font-medium">YES Bid</th>
                  <th className="pb-2 pr-4 font-medium">NO Bid</th>
                  <th className="pb-2 pr-4 font-medium">YES Ask Size</th>
                  <th className="pb-2 font-medium">Decimal Odds</th>
                </tr>
              </thead>
              <tbody>
                {markets.map((m) => (
                  <MarketRow key={m.ticker} market={m} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function MarketRow({ market: m }: { market: KalshiMarketResponse }) {
  const isOU25 = m.floor_strike === OU25_STRIKE;
  return (
    <tr
      className={`border-b border-border/50 hover:bg-muted/30 ${isOU25 ? "border-l-2 border-l-accent bg-accent/5" : ""}`}
    >
      <td className="py-2 pr-4 font-mono text-xs">
        <Link
          href={`/kalshi/markets/${m.ticker}`}
          className="text-accent hover:underline"
        >
          {m.ticker}
        </Link>
      </td>
      <td className="py-2 pr-4 font-mono">{m.floor_strike}</td>
      <td className="py-2 pr-4 font-mono">{m.yes_bid}</td>
      <td className="py-2 pr-4 font-mono">{m.no_bid}</td>
      <td className="py-2 pr-4 font-mono">
        {m.yes_ask_size != null ? m.yes_ask_size : "—"}
      </td>
      <td className="py-2 font-mono">{m.decimal_odds ?? "—"}</td>
    </tr>
  );
}

function AliasCard({
  status,
  fixtureId,
}: {
  status: string | null;
  fixtureId: string | null;
}) {
  const [showBootstrap, setShowBootstrap] = useState(false);

  if (status === "resolved" && fixtureId) {
    return (
      <div className="rounded-md border border-success/30 bg-success/10 px-4 py-3">
        <div className="flex items-center gap-2">
          <LinkIcon size={14} className="text-success" />
          <span className="text-sm font-medium text-success">Resolved</span>
        </div>
        <Link
          href={`/fixtures/${fixtureId}`}
          className="mt-1 flex items-center gap-1 font-mono text-xs text-accent hover:underline"
        >
          {fixtureId}
          <ExternalLink size={10} />
        </Link>
      </div>
    );
  }

  return (
    <>
      <div className="rounded-md border border-yellow-500/30 bg-yellow-500/10 px-4 py-3">
        <div className="flex items-center gap-2">
          <LinkIcon size={14} className="text-yellow-500" />
          <span className="text-sm font-medium text-yellow-500">Unresolved</span>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="mt-2"
          onClick={() => setShowBootstrap(true)}
        >
          Bootstrap this event
        </Button>
      </div>
      {showBootstrap && (
        <BootstrapModal onClose={() => setShowBootstrap(false)} />
      )}
    </>
  );
}
