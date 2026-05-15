"use client";

import { useEffect, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useBankroll,
  useExposure,
  useKellyPreview,
  useBets,
} from "@/lib/api/hooks";
import type {
  BankrollResponse,
  ExposureResponse,
  KellyPreviewRequest,
  KellyPreviewResponse,
} from "@/lib/api/hooks";
import BankrollSparkline from "@/components/charts/BankrollSparkline";
import StakesHistogram from "@/components/charts/StakesHistogram";

const DEFAULT_PARAMS: KellyPreviewRequest = {
  p_hat: 0.55,
  sigma_p: 0.02,
  odds: 2.1,
  base_fraction: 0.25,
  uncertainty_k: 1.0,
  per_bet_cap_pct: 0.02,
  recent_clv_pct: 0.0,
  bankroll: "1000",
};

export default function RiskPage() {
  const { data: bankroll, isLoading: bkLoading, refetch: refetchBk } = useBankroll();
  const { data: exposure, isLoading: exLoading, refetch: refetchEx } = useExposure();
  const { data: recentBets } = useBets({ limit: 100, offset: 0 });

  function handleRefresh() {
    void refetchBk();
    void refetchEx();
  }

  const stakes = (recentBets?.bets ?? []).map((b) => b.stake_gbp);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Risk</h1>
          <p className="text-sm text-muted-foreground">
            Bankroll, open exposure, and Kelly stake calculator
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleRefresh}
          disabled={bkLoading || exLoading}
        >
          {bkLoading || exLoading ? (
            <Loader2 size={14} className="mr-2 animate-spin" />
          ) : (
            <RefreshCw size={14} className="mr-2" />
          )}
          Refresh
        </Button>
      </div>

      {/* Top row: bankroll + exposure */}
      <div className="grid gap-6 lg:grid-cols-2">
        <BankrollPanel data={bankroll} isLoading={bkLoading} />
        <ExposurePanel data={exposure} isLoading={exLoading} />
      </div>

      {/* Kelly preview tool */}
      <KellyPreviewTool />

      {/* Recent stakes histogram */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Stakes Distribution</CardTitle>
        </CardHeader>
        <CardContent>
          <StakesHistogram stakes={stakes} />
        </CardContent>
      </Card>
    </div>
  );
}

function BankrollPanel({
  data,
  isLoading,
}: {
  data: BankrollResponse | undefined;
  isLoading: boolean;
}) {
  const drawdownPct = data ? data.drawdown_pct * 100 : 0;
  const drawdownCls = drawdownPct > 10 ? "text-red-500" : "text-foreground";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Bankroll</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <div className="flex h-24 items-center justify-center">
            <Loader2 size={20} className="animate-spin text-muted-foreground" />
          </div>
        ) : data ? (
          <>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <p className="text-xs text-muted-foreground">Current</p>
                <p className="text-2xl font-bold tabular-nums">£{data.current}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Peak</p>
                <p className="text-lg font-semibold tabular-nums">£{data.peak}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Drawdown</p>
                <p className={`text-lg font-semibold tabular-nums ${drawdownCls}`}>
                  {drawdownPct.toFixed(2)}%
                </p>
              </div>
            </div>
            <BankrollSparkline data={data.sparkline} />
          </>
        ) : (
          <p className="text-sm text-muted-foreground">No bankroll data.</p>
        )}
      </CardContent>
    </Card>
  );
}

function ExposurePanel({
  data,
  isLoading,
}: {
  data: ExposureResponse | undefined;
  isLoading: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Open Exposure</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <div className="flex h-24 items-center justify-center">
            <Loader2 size={20} className="animate-spin text-muted-foreground" />
          </div>
        ) : data ? (
          <>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-muted-foreground">Today open</p>
                <p className="text-2xl font-bold tabular-nums">£{data.today_open}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total open</p>
                <p className="text-2xl font-bold tabular-nums">£{data.total_open}</p>
              </div>
            </div>
            {data.per_fixture.length > 0 ? (
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border bg-muted/50 text-left text-xs text-muted-foreground">
                      <th className="px-3 py-2 font-medium">Fixture</th>
                      <th className="px-3 py-2 text-right font-medium">Open stake</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.per_fixture.map((f) => (
                      <tr
                        key={f.fixture_id}
                        className="border-b border-border/50 hover:bg-muted/30"
                      >
                        <td className="px-3 py-2 font-mono text-xs">{f.fixture_id}</td>
                        <td className="px-3 py-2 text-right font-mono text-xs">
                          £{f.open_stake}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-center text-sm text-muted-foreground">
                No open positions.
              </p>
            )}
          </>
        ) : (
          <p className="text-sm text-muted-foreground">No exposure data.</p>
        )}
      </CardContent>
    </Card>
  );
}

function KellyPreviewTool() {
  const [params, setParams] = useState<KellyPreviewRequest>(DEFAULT_PARAMS);
  const [bankrollInput, setBankrollInput] = useState(DEFAULT_PARAMS.bankroll);
  const [result, setResult] = useState<KellyPreviewResponse | null>(null);

  const { mutate: runPreview, isPending } = useKellyPreview();

  // 200ms debounce on every param change — mutate is stable across renders
  useEffect(() => {
    const timer = setTimeout(() => {
      runPreview(params, { onSuccess: (data) => setResult(data) });
    }, 200);
    return () => clearTimeout(timer);
  }, [params, runPreview]);

  function setNum(key: keyof KellyPreviewRequest, value: number) {
    setParams((p) => ({ ...p, [key]: value }));
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Kelly Preview</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Sliders */}
          <div className="space-y-3">
            <SliderRow
              label="p_hat"
              value={params.p_hat}
              min={0.01}
              max={0.99}
              step={0.01}
              onChange={(v) => setNum("p_hat", v)}
              format={(v) => v.toFixed(2)}
            />
            <SliderRow
              label="σ_p"
              value={params.sigma_p}
              min={0}
              max={0.2}
              step={0.005}
              onChange={(v) => setNum("sigma_p", v)}
              format={(v) => v.toFixed(3)}
            />
            <SliderRow
              label="Odds"
              value={params.odds}
              min={1.01}
              max={20.0}
              step={0.01}
              onChange={(v) => setNum("odds", v)}
              format={(v) => v.toFixed(2)}
            />
            <SliderRow
              label="Base fraction"
              value={params.base_fraction}
              min={0.05}
              max={1.0}
              step={0.05}
              onChange={(v) => setNum("base_fraction", v)}
              format={(v) => v.toFixed(2)}
            />
            <SliderRow
              label="Uncertainty k"
              value={params.uncertainty_k}
              min={0}
              max={3.0}
              step={0.1}
              onChange={(v) => setNum("uncertainty_k", v)}
              format={(v) => v.toFixed(1)}
            />
            <SliderRow
              label="Per-bet cap"
              value={params.per_bet_cap_pct}
              min={0.005}
              max={0.05}
              step={0.005}
              onChange={(v) => setNum("per_bet_cap_pct", v)}
              format={(v) => `${(v * 100).toFixed(1)}%`}
            />
            <SliderRow
              label="Recent CLV"
              value={params.recent_clv_pct}
              min={-0.1}
              max={0.1}
              step={0.005}
              onChange={(v) => setNum("recent_clv_pct", v)}
              format={(v) => `${(v * 100).toFixed(1)}%`}
            />
            {/* Bankroll text input */}
            <div className="grid grid-cols-3 items-center gap-4">
              <label className="text-right text-sm text-muted-foreground">
                Bankroll (£)
              </label>
              <input
                type="text"
                value={bankrollInput}
                onChange={(e) => {
                  setBankrollInput(e.target.value);
                  const parsed = parseFloat(e.target.value);
                  if (!isNaN(parsed) && parsed > 0) {
                    setParams((p) => ({ ...p, bankroll: e.target.value }));
                  }
                }}
                className="col-span-2 rounded-md border border-border bg-background px-3 py-1.5 font-mono text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                placeholder="1000"
              />
            </div>
          </div>

          {/* Result panel */}
          <div className="rounded-lg border border-border bg-muted/30 p-4">
            {isPending ? (
              <div className="flex h-full items-center justify-center">
                <Loader2 size={20} className="animate-spin text-muted-foreground" />
              </div>
            ) : result ? (
              <div className="space-y-3">
                <div className="flex items-baseline gap-2">
                  <p className="text-4xl font-bold tabular-nums">£{result.stake}</p>
                  {result.per_bet_cap_hit && (
                    <Badge variant="destructive" className="text-xs">
                      cap hit
                    </Badge>
                  )}
                </div>
                <div className="space-y-1.5 text-sm">
                  <PreviewRow label="p_lb" value={result.p_lb.toFixed(4)} />
                  <PreviewRow label="f_full" value={result.f_full.toFixed(4)} />
                  <PreviewRow
                    label="CLV multiplier"
                    value={result.clv_multiplier.toFixed(2)}
                  />
                  <PreviewRow label="f_used" value={result.f_used.toFixed(4)} />
                </div>
              </div>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                Adjust sliders to see stake estimate.
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function SliderRow({
  label,
  value,
  min,
  max,
  step,
  onChange,
  format,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  format?: (v: number) => string;
}) {
  return (
    <div className="grid grid-cols-3 items-center gap-4">
      <label className="text-right text-sm text-muted-foreground">{label}</label>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full accent-primary"
      />
      <span className="font-mono text-sm tabular-nums">
        {format ? format(value) : value}
      </span>
    </div>
  );
}

function PreviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono font-medium tabular-nums">{value}</span>
    </div>
  );
}
