"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  usePredictionDetail,
  usePredictionFeatures,
  useRunPredictions,
} from "@/lib/api/hooks";
import type { PredictionResponse, PredictionFeatureItem } from "@/lib/api/hooks";

export default function PredictionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const predictionId = decodeURIComponent(id);

  const { data, isLoading, error } = usePredictionDetail(predictionId);
  const { data: featuresData, isLoading: featuresLoading } =
    usePredictionFeatures(predictionId);
  const runMutation = useRunPredictions();

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
          href="/predictions"
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft size={14} />
          Predictions
        </Link>
        <p className="text-sm text-destructive">Prediction not found.</p>
      </div>
    );
  }

  function handleRerun() {
    runMutation.mutate([data!.fixture_id], {
      onSuccess: (res) => {
        toast.success(`Re-run started — job_id: ${res.job_id}`);
      },
      onError: (err) => {
        toast.error(err instanceof Error ? err.message : "Failed to start re-run");
      },
    });
  }

  return (
    <div className="space-y-6">
      <Link
        href="/predictions"
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft size={14} />
        Predictions
      </Link>

      <PredictionHeader prediction={data} onRerun={handleRerun} rerunPending={runMutation.isPending} />

      <div className="grid gap-4 lg:grid-cols-2">
        <ProbabilityPanel prediction={data} />

        <Card>
          <CardHeader>
            <CardTitle>Feature Vector</CardTitle>
          </CardHeader>
          <CardContent>
            {featuresLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 size={16} className="animate-spin text-muted-foreground" />
              </div>
            ) : featuresData?.error ? (
              <p className="text-sm text-destructive">{featuresData.error}</p>
            ) : (featuresData?.features ?? []).length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">
                No features available.
              </p>
            ) : (
              <FeatureTable features={featuresData!.features} />
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Metadata</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          <Row label="Prediction ID" value={<span className="font-mono text-xs">{data.prediction_id}</span>} />
          <Row label="Features hash" value={<span className="font-mono text-xs">{data.features_hash}</span>} />
          {data.run_id && (
            <Row label="Run ID" value={<span className="font-mono text-xs">{data.run_id}</span>} />
          )}
          {data.generated_at && (
            <Row
              label="Generated at"
              value={new Date(data.generated_at).toLocaleString("en-GB")}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function PredictionHeader({
  prediction: p,
  onRerun,
  rerunPending,
}: {
  prediction: PredictionResponse;
  onRerun: () => void;
  rerunPending: boolean;
}) {
  const asOfStr = p.as_of
    ? new Date(p.as_of).toLocaleString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZoneName: "short",
      })
    : "—";

  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{p.market}</Badge>
          <Badge variant="secondary">{p.selection}</Badge>
          <span className="text-xs text-muted-foreground">{p.model_version}</span>
        </div>
        <Link
          href={`/fixtures/${encodeURIComponent(p.fixture_id)}`}
          className="font-mono text-xs text-accent hover:underline"
          title="Open fixture"
        >
          {p.fixture_id}
        </Link>
        <p className="text-xs text-muted-foreground">as of {asOfStr}</p>
      </div>
      <Button
        size="sm"
        variant="outline"
        onClick={onRerun}
        disabled={rerunPending}
      >
        {rerunPending ? (
          <Loader2 size={14} className="mr-2 animate-spin" />
        ) : (
          <RotateCcw size={14} className="mr-2" />
        )}
        Re-run for this fixture
      </Button>
    </div>
  );
}

function ProbabilityPanel({ prediction: p }: { prediction: PredictionResponse }) {
  const ci =
    p.sigma_p != null
      ? {
          lo: Math.max(0, p.p_calibrated - 1.96 * p.sigma_p),
          hi: Math.min(1, p.p_calibrated + 1.96 * p.sigma_p),
        }
      : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Probabilities</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-lg border border-border p-4 text-center">
            <p className="text-xs text-muted-foreground">p_raw</p>
            <p className="mt-1 font-mono text-2xl font-bold tabular-nums">
              {p.p_raw.toFixed(4)}
            </p>
          </div>
          <div className="rounded-lg border border-primary/30 bg-primary/5 p-4 text-center">
            <p className="text-xs text-muted-foreground">p_calibrated</p>
            <p className="mt-1 font-mono text-2xl font-bold tabular-nums">
              {p.p_calibrated.toFixed(4)}
            </p>
          </div>
        </div>

        {p.sigma_p != null && (
          <div className="space-y-1 text-sm">
            <Row
              label="σ_p (std dev)"
              value={<span className="font-mono">{p.sigma_p.toFixed(4)}</span>}
            />
            {ci && (
              <Row
                label="95% CI"
                value={
                  <span className="font-mono">
                    [{ci.lo.toFixed(4)}, {ci.hi.toFixed(4)}]
                  </span>
                }
              />
            )}
          </div>
        )}

        <div className="rounded-md bg-muted/30 p-3 text-xs text-muted-foreground">
          Implied odds (1 / p_cal):{" "}
          <span className="font-mono font-medium text-foreground">
            {(1 / p.p_calibrated).toFixed(3)}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

function FeatureTable({ features }: { features: PredictionFeatureItem[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted-foreground">
            <th className="pb-2 font-medium">Feature</th>
            <th className="pb-2 text-right font-medium">Value</th>
          </tr>
        </thead>
        <tbody>
          {features.map((f) => (
            <tr key={f.name} className="border-b border-border/40">
              <td className="py-1.5 pr-4">
                <span
                  className="cursor-help font-mono text-xs underline decoration-dotted"
                  title={f.description}
                >
                  {f.name}
                </span>
              </td>
              <td className="py-1.5 text-right font-mono text-xs tabular-nums">
                {f.value != null ? f.value.toFixed(4) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Row({
  label,
  value,
}: {
  label: string;
  value: string | React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}
