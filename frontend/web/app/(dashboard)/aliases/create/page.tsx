"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, CheckCircle2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCreateAlias, useBootstrapPreview } from "@/lib/api/hooks";

export default function CreateAliasPage() {
  const router = useRouter();
  const [eventTicker, setEventTicker] = useState("");
  const [fixtureId, setFixtureId] = useState("");
  const [confidence, setConfidence] = useState("1.0");
  const [resolvedBy, setResolvedBy] = useState("manual");

  const createMutation = useCreateAlias();
  const { data: previewData, refetch: runPreview, isFetching: previewLoading } =
    useBootstrapPreview();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!eventTicker.trim() || !fixtureId.trim()) {
      toast.error("Event ticker and fixture ID are required.");
      return;
    }
    const conf = parseFloat(confidence);
    if (isNaN(conf) || conf < 0 || conf > 1) {
      toast.error("Confidence must be between 0 and 1.");
      return;
    }
    createMutation.mutate(
      {
        event_ticker: eventTicker.trim(),
        fixture_id: fixtureId.trim(),
        confidence: conf,
        resolved_by: resolvedBy.trim() || "manual",
      },
      {
        onSuccess: (data) => {
          toast.success(
            `Alias created: ${data.event_ticker} → ${data.fixture_id}`,
          );
          router.push("/aliases");
        },
        onError: (e) => toast.error(e.message),
      },
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {/* Back link */}
      <Link
        href="/aliases"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft size={14} />
        Back to Aliases
      </Link>

      <h1 className="text-2xl font-bold">Create Manual Alias</h1>
      <p className="text-sm text-muted-foreground">
        Map a Kalshi event ticker to a fixture in the warehouse. The fixture
        must already exist in <code>v_fixtures_epl</code> or{" "}
        <code>synthetic_fixtures</code>.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="rounded-lg border border-border bg-card p-4 space-y-4">
          <div>
            <label
              htmlFor="event_ticker"
              className="mb-1 block text-sm font-medium"
            >
              Event Ticker
            </label>
            <Input
              id="event_ticker"
              placeholder="e.g. KXEPLTOTAL-26MAY23-ARS-MCI"
              value={eventTicker}
              onChange={(e) => setEventTicker(e.target.value)}
              className="font-mono"
            />
          </div>

          <div>
            <label
              htmlFor="fixture_id"
              className="mb-1 block text-sm font-medium"
            >
              Fixture ID
            </label>
            <Input
              id="fixture_id"
              placeholder="e.g. epl_2025-05-26_ARS_MCI"
              value={fixtureId}
              onChange={(e) => setFixtureId(e.target.value)}
              className="font-mono"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              The fixture must exist in the warehouse. The backend validates
              this before creating the alias.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="confidence"
                className="mb-1 block text-sm font-medium"
              >
                Confidence (0–1)
              </label>
              <Input
                id="confidence"
                type="number"
                step="0.01"
                min="0"
                max="1"
                value={confidence}
                onChange={(e) => setConfidence(e.target.value)}
                className="font-mono"
              />
            </div>
            <div>
              <label
                htmlFor="resolved_by"
                className="mb-1 block text-sm font-medium"
              >
                Resolved By
              </label>
              <Input
                id="resolved_by"
                value={resolvedBy}
                onChange={(e) => setResolvedBy(e.target.value)}
              />
            </div>
          </div>
        </div>

        {/* Preview section */}
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium">Bootstrap Preview</h3>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void runPreview()}
              disabled={previewLoading}
            >
              {previewLoading ? (
                <Loader2 size={14} className="mr-2 animate-spin" />
              ) : (
                <CheckCircle2 size={14} className="mr-2" />
              )}
              Dry Run
            </Button>
          </div>
          {previewData && (
            <div className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
              <Stat label="Total Events" value={previewData.total_events} />
              <Stat
                label="Already Mapped"
                value={previewData.already_mapped}
              />
              <Stat label="Would Resolve" value={previewData.would_resolve} />
              <Stat label="Would Skip" value={previewData.would_skip} />
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2">
          <Link href="/aliases">
            <Button type="button" variant="outline">
              Cancel
            </Button>
          </Link>
          <Button type="submit" disabled={createMutation.isPending}>
            {createMutation.isPending && (
              <Loader2 size={14} className="mr-2 animate-spin" />
            )}
            Create Alias
          </Button>
        </div>
      </form>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border/50 p-2 text-center">
      <p className="text-lg font-semibold">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
