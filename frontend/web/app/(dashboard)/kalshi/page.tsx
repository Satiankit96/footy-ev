"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  useKalshiCredentials,
  useKalshiHealthCheck,
  useKalshiEvents,
} from "@/lib/api/hooks";
import type {
  KalshiCredentialsResponse,
  KalshiHealthResponse,
  KalshiEventResponse,
  KalshiMarketResponse,
} from "@/lib/api/hooks";

type TabId = "events" | "markets";

export default function KalshiPage() {
  const { data: creds } = useKalshiCredentials();
  const healthCheck = useKalshiHealthCheck();
  const [healthResult, setHealthResult] = useState<KalshiHealthResponse | null>(
    null,
  );
  const {
    data: eventsData,
    refetch: refetchEvents,
    isFetching: eventsFetching,
  } = useKalshiEvents();
  const [activeTab, setActiveTab] = useState<TabId>("events");

  function handleHealthCheck() {
    healthCheck.mutate(undefined, {
      onSuccess: (data) => {
        setHealthResult(data);
        if (data.ok) toast.success(`Kalshi OK · ${data.latency_ms}ms`);
        else toast.error(`Kalshi health check failed: ${data.error}`);
      },
      onError: (e) => toast.error(e.message),
    });
  }

  function handleRefreshEvents() {
    void refetchEvents();
  }

  const allMarkets: (KalshiMarketResponse & { _event_title?: string })[] = [];

  return (
    <div className="space-y-6">
      {/* Credentials banner */}
      <CredentialsBanner creds={creds ?? null} />

      {/* Health check */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-card p-4">
        <Button
          onClick={handleHealthCheck}
          disabled={healthCheck.isPending}
          variant="outline"
          size="sm"
        >
          {healthCheck.isPending ? (
            <Loader2 size={14} className="mr-2 animate-spin" />
          ) : (
            <Activity size={14} className="mr-2" />
          )}
          Check Connection
        </Button>
        {healthResult && <HealthResult result={healthResult} />}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border">
        {(["events", "markets"] as TabId[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab
                ? "border-b-2 border-accent text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab === "events" ? "Events" : "Markets"}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "events" && (
        <EventsTab
          creds={creds ?? null}
          events={eventsData?.events ?? []}
          loading={eventsFetching}
          onRefresh={handleRefreshEvents}
        />
      )}
      {activeTab === "markets" && (
        <MarketsTab creds={creds ?? null} markets={allMarkets} />
      )}
    </div>
  );
}

function CredentialsBanner({
  creds,
}: {
  creds: KalshiCredentialsResponse | null;
}) {
  if (!creds) return null;

  if (creds.configured) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-success/30 bg-success/10 p-4">
        <CheckCircle2 size={18} className="text-success" />
        <div>
          <p className="text-sm font-medium text-success">
            Kalshi Connected · {creds.is_demo ? "DEMO" : "PROD"}
          </p>
          <p className="font-mono text-xs text-muted-foreground">
            {creds.base_url}
          </p>
        </div>
      </div>
    );
  }

  const missing: string[] = [];
  if (!creds.key_id_present) missing.push("KALSHI_API_KEY_ID");
  if (!creds.private_key_present) missing.push("Private key file");
  if (!creds.base_url) missing.push("KALSHI_API_BASE_URL");

  return (
    <div className="flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/10 p-4">
      <XCircle size={18} className="mt-0.5 text-destructive" />
      <div>
        <p className="text-sm font-medium text-destructive">
          Kalshi Not Configured
        </p>
        <ul className="mt-1 list-inside list-disc text-xs text-muted-foreground">
          {missing.map((m) => (
            <li key={m}>{m} — not set</li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-muted-foreground">
          See <code>docs/SETUP_GUIDE.md</code> for onboarding instructions.
        </p>
      </div>
    </div>
  );
}

function HealthResult({ result }: { result: KalshiHealthResponse }) {
  return (
    <div className="flex items-center gap-4 text-sm">
      {result.ok ? (
        <CheckCircle2 size={16} className="text-success" />
      ) : (
        <XCircle size={16} className="text-destructive" />
      )}
      {result.latency_ms != null && (
        <span className="font-mono">
          {result.latency_ms}
          <span className="text-muted-foreground">ms</span>
        </span>
      )}
      {result.clock_skew_s != null && (
        <span className="font-mono">
          skew {result.clock_skew_s}
          <span className="text-muted-foreground">s</span>
        </span>
      )}
      {result.clock_skew_s != null && result.clock_skew_s > 10 && (
        <span className="flex items-center gap-1 text-xs text-yellow-500">
          <AlertTriangle size={12} />
          Clock skew detected. RSA signing may fail. Sync your system clock.
        </span>
      )}
      {result.error && (
        <span className="text-xs text-destructive">{result.error}</span>
      )}
    </div>
  );
}

function EventsTab({
  creds,
  events,
  loading,
  onRefresh,
}: {
  creds: KalshiCredentialsResponse | null;
  events: KalshiEventResponse[];
  loading: boolean;
  onRefresh: () => void;
}) {
  if (!creds?.configured) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Configure Kalshi credentials to browse events.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <Button variant="outline" size="sm" onClick={onRefresh}>
          {loading ? (
            <Loader2 size={14} className="mr-2 animate-spin" />
          ) : (
            <RefreshCw size={14} className="mr-2" />
          )}
          Refresh
        </Button>
        <span className="text-xs text-muted-foreground">
          {events.length} events
        </span>
      </div>

      {events.length === 0 && !loading ? (
        <p className="py-8 text-center text-sm text-muted-foreground">
          No events loaded. Click Refresh to fetch from Kalshi.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50 text-left text-muted-foreground">
                <th className="px-3 py-2 font-medium">Event Ticker</th>
                <th className="px-3 py-2 font-medium">Title</th>
                <th className="px-3 py-2 font-medium">Alias Status</th>
                <th className="px-3 py-2 font-medium">Fixture</th>
                <th className="px-3 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr
                  key={e.event_ticker}
                  className="border-b border-border/50 hover:bg-muted/30"
                >
                  <td className="px-3 py-2 font-mono text-xs">
                    {e.event_ticker}
                  </td>
                  <td className="px-3 py-2">{e.title}</td>
                  <td className="px-3 py-2">
                    <AliasBadge status={e.alias_status} />
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {e.fixture_id ? (
                      <Link
                        href={`/fixtures/${e.fixture_id}`}
                        className="text-accent hover:underline"
                      >
                        {e.fixture_id}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <Link
                      href={`/kalshi/events/${e.event_ticker}`}
                      className="text-accent hover:underline"
                    >
                      View
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function MarketsTab({
  creds,
  markets,
}: {
  creds: KalshiCredentialsResponse | null;
  markets: KalshiMarketResponse[];
}) {
  if (!creds?.configured) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Configure Kalshi credentials to browse markets.
      </p>
    );
  }

  if (markets.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Load events first to populate the markets view.
      </p>
    );
  }

  const sorted = [...markets].sort((a, b) => {
    const aP = parseFloat(a.implied_probability ?? "0");
    const bP = parseFloat(b.implied_probability ?? "0");
    return bP - aP;
  });

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/50 text-left text-muted-foreground">
            <th className="px-3 py-2 font-medium">Market Ticker</th>
            <th className="px-3 py-2 font-medium">Event</th>
            <th className="px-3 py-2 font-medium">Floor Strike</th>
            <th className="px-3 py-2 font-medium">YES Bid</th>
            <th className="px-3 py-2 font-medium">NO Bid</th>
            <th className="px-3 py-2 font-medium">Implied Prob</th>
            <th className="px-3 py-2 font-medium">Decimal Odds</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((m) => (
            <tr
              key={m.ticker}
              className="border-b border-border/50 hover:bg-muted/30"
            >
              <td className="px-3 py-2 font-mono text-xs">
                <Link
                  href={`/kalshi/markets/${m.ticker}`}
                  className="text-accent hover:underline"
                >
                  {m.ticker}
                </Link>
              </td>
              <td className="px-3 py-2 font-mono text-xs">{m.event_ticker}</td>
              <td className="px-3 py-2 font-mono">{m.floor_strike}</td>
              <td className="px-3 py-2 font-mono">{m.yes_bid}</td>
              <td className="px-3 py-2 font-mono">{m.no_bid}</td>
              <td className="px-3 py-2 font-mono">
                {m.implied_probability ? `${m.implied_probability}%` : "—"}
              </td>
              <td className="px-3 py-2 font-mono">
                {m.decimal_odds ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AliasBadge({ status }: { status: string | null }) {
  if (status === "resolved") {
    return (
      <span className="inline-flex items-center rounded-full bg-success/20 px-2 py-0.5 text-xs font-medium text-success">
        Resolved
      </span>
    );
  }
  if (status === "unresolved") {
    return (
      <span className="inline-flex items-center rounded-full bg-yellow-500/20 px-2 py-0.5 text-xs font-medium text-yellow-500">
        Unresolved
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
      None
    </span>
  );
}
