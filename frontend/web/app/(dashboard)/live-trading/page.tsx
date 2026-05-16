"use client";

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Loader2,
  ShieldOff,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLiveTradingStatus, useCheckConditions } from "@/lib/api/hooks";
import type { ClvConditionResult, BankrollConditionResult } from "@/lib/api/hooks";

function ClvConditionCard({ result }: { result: ClvConditionResult }) {
  const icon = result.met ? (
    <CheckCircle2 className="h-5 w-5 text-green-500 flex-shrink-0" />
  ) : (
    <XCircle className="h-5 w-5 text-destructive flex-shrink-0" />
  );

  const clvSign = result.mean_clv_pct >= 0 ? "+" : "";
  const observed = `${result.bet_count} settled bets · ${result.days_span} days · CLV ${clvSign}${(result.mean_clv_pct * 100).toFixed(2)}%`;
  const required = "Requires: 1,000+ bets · 60+ days · mean CLV > 0%";

  return (
    <div className="flex items-start gap-3 rounded-lg border p-4">
      {icon}
      <div className="flex flex-col gap-1">
        <p className="font-medium text-sm">
          Positive CLV on 1,000+ settled bets over 60+ days
        </p>
        <p className="text-xs text-muted-foreground">
          Current: {observed}
        </p>
        <p className="text-xs text-muted-foreground">{required}</p>
      </div>
    </div>
  );
}

function BankrollConditionCard({ result }: { result: BankrollConditionResult }) {
  const icon = result.met ? (
    <CheckCircle2 className="h-5 w-5 text-green-500 flex-shrink-0" />
  ) : (
    <XCircle className="h-5 w-5 text-destructive flex-shrink-0" />
  );

  return (
    <div className="flex items-start gap-3 rounded-lg border p-4">
      {icon}
      <div className="flex flex-col gap-1">
        <p className="font-medium text-sm">
          Operator has confirmed disposable bankroll
        </p>
        <p className="text-xs text-muted-foreground">
          Flag {result.flag_name}:{" "}
          {result.flag_set ? (
            <span className="text-green-600 font-medium">set</span>
          ) : (
            <span className="text-destructive font-medium">not set</span>
          )}
        </p>
        <p className="text-xs text-muted-foreground">
          Requires: <code className="font-mono">{result.flag_name}=true</code> in{" "}
          <code className="font-mono">.env</code>
        </p>
      </div>
    </div>
  );
}

export default function LiveTradingPage() {
  const { data: status, isLoading: statusLoading } = useLiveTradingStatus();
  const { mutate: checkConditions, isPending: checking, data: conditions } =
    useCheckConditions();
  const [checkError, setCheckError] = useState<string | null>(null);

  function handleCheck() {
    setCheckError(null);
    checkConditions(undefined, {
      onError: (err) =>
        setCheckError(err instanceof Error ? err.message : String(err)),
    });
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Big red banner — always visible */}
      <div className="flex items-center gap-3 rounded-lg bg-destructive px-6 py-5 text-destructive-foreground">
        <ShieldOff className="h-7 w-7 flex-shrink-0" />
        <div>
          <p className="text-xl font-bold tracking-wide">LIVE TRADING IS DISABLED</p>
          <p className="text-sm opacity-90">
            Paper-trading mode only. Both gate conditions must be met before going live.
          </p>
        </div>
      </div>

      {/* Gate status */}
      {statusLoading ? (
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading status…
        </div>
      ) : status ? (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              Gate Reasons
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1">
              {status.gate_reasons.map((reason, i) => (
                <li key={i} className="text-sm text-muted-foreground flex items-start gap-2">
                  <span className="text-destructive mt-0.5">•</span>
                  {reason}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {/* Condition checker */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">Gate Conditions (§3 Bankroll Discipline)</CardTitle>
          <Button
            variant="outline"
            size="sm"
            onClick={handleCheck}
            disabled={checking}
          >
            {checking ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            Check conditions
          </Button>
        </CardHeader>
        <CardContent>
          {checkError && (
            <p className="mb-3 text-sm text-destructive">{checkError}</p>
          )}
          {conditions ? (
            <div className="flex flex-col gap-3">
              <ClvConditionCard result={conditions.clv_condition} />
              <BankrollConditionCard result={conditions.bankroll_condition} />
              <div
                className={`rounded-lg px-4 py-2 text-sm font-medium ${
                  conditions.all_met
                    ? "bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300"
                    : "bg-destructive/10 text-destructive"
                }`}
              >
                {conditions.all_met
                  ? "Both conditions met — see the note below before enabling."
                  : "Conditions not yet met. Continue paper trading."}
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Click &quot;Check conditions&quot; to evaluate your gate status against the warehouse.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Documentation panel */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">What each condition means</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4 text-sm text-muted-foreground">
          <div>
            <p className="font-semibold text-foreground mb-1">
              Condition 1 — Positive CLV on 1,000+ bets over 60+ days
            </p>
            <p>
              Closing-line value (CLV) measures whether your model beats the market price at
              match kickoff. A positive mean CLV on a large sample over multiple months
              distinguishes genuine edge from short-run luck — 1,000 bets is the minimum
              sample for statistical significance, and 60 days ensures the sample spans
              varied market conditions.
            </p>
          </div>
          <div>
            <p className="font-semibold text-foreground mb-1">
              Condition 2 — Confirmed disposable bankroll
            </p>
            <p>
              Even a profitable system can suffer 20–30% drawdowns. The{" "}
              <code className="font-mono text-xs">BANKROLL_DISCIPLINE_CONFIRMED</code> flag
              is your explicit acknowledgment that the capital you are risking is money you
              can afford to lose 50% of without affecting rent, food, tuition, or any
              essential expense. No algorithm can enforce this — only you can.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Footer note — no enable button anywhere on this page */}
      <p className="text-xs text-muted-foreground border rounded-lg px-4 py-3">
        To enable live trading, set{" "}
        <code className="font-mono">LIVE_TRADING=true</code> in{" "}
        <code className="font-mono">.env</code> after both conditions above are met.
        This cannot be done through the UI.
      </p>
    </div>
  );
}
