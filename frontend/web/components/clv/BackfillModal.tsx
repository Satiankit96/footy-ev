"use client";

import { useState, useCallback, useRef } from "react";
import { Loader2, X, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useClvBackfill } from "@/lib/api/hooks";
import { useWebSocket } from "@/lib/api/ws";

interface ProgressEvent {
  type: string;
  payload: {
    job_id: string;
    step?: string;
    message?: string;
    percent?: number;
    status?: string;
    error?: string;
  };
}

type Phase = "form" | "running" | "completed" | "failed";

export function BackfillModal({ onClose }: { onClose: () => void }) {
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [phase, setPhase] = useState<Phase>("form");
  const [jobId, setJobId] = useState<string | null>(null);
  const [logs, setLogs] = useState<ProgressEvent[]>([]);
  const [percent, setPercent] = useState(0);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const backfillMutation = useClvBackfill();

  const handleWsMessage = useCallback((event: ProgressEvent) => {
    setLogs((prev) => [...prev, event]);
    if (event.payload.percent) setPercent(event.payload.percent);
    if (event.type === "completed") setPhase("completed");
    else if (event.type === "failed") setPhase("failed");
  }, []);

  useWebSocket<ProgressEvent>(
    jobId ? `/ws/v1/jobs/${jobId}` : "",
    { enabled: !!jobId && phase === "running", onMessage: handleWsMessage },
  );

  function handleRun() {
    backfillMutation.mutate(
      { from_date: fromDate || undefined, to_date: toDate || undefined },
      {
        onSuccess: (res) => {
          setJobId(res.job_id);
          setPhase("running");
          setLogs([]);
          setPercent(0);
          toast.success(`CLV backfill started — job_id: ${res.job_id}`);
        },
        onError: (err) => {
          toast.error(err instanceof Error ? err.message : "Failed to start backfill");
        },
      },
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="flex w-full max-w-lg flex-col rounded-lg border border-border bg-card shadow-lg">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-lg font-semibold">Backfill CLV</h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="space-y-4 p-4">
          {phase === "form" && (
            <>
              <p className="text-sm text-muted-foreground">
                Populates <code>closing_odds</code> and <code>clv_pct</code> for
                settled bets that are missing CLV data. Queries Kalshi live
                snapshots then falls back to Pinnacle historical prices.
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">From date (optional)</label>
                  <Input
                    type="date"
                    value={fromDate}
                    onChange={(e) => setFromDate(e.target.value)}
                    className="text-sm"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">To date (optional)</label>
                  <Input
                    type="date"
                    value={toDate}
                    onChange={(e) => setToDate(e.target.value)}
                    className="text-sm"
                  />
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Leave blank to process all settled bets with missing CLV.
              </p>
            </>
          )}

          {(phase === "running" || phase === "completed" || phase === "failed") && (
            <div className="space-y-3">
              {/* Progress bar */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">
                    {phase === "running" ? "Running…" : phase === "completed" ? "Completed" : "Failed"}
                  </span>
                  <span className="font-mono">{percent}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className={`h-full transition-all duration-300 ${
                      phase === "failed" ? "bg-destructive" : "bg-primary"
                    }`}
                    style={{ width: `${percent}%` }}
                  />
                </div>
              </div>

              {/* Log drawer */}
              <div className="rounded-md border border-border bg-muted/30 p-3">
                <p className="mb-2 text-xs font-medium text-muted-foreground">
                  Progress log ({logs.length} events)
                </p>
                <div className="max-h-40 overflow-y-auto font-mono text-xs">
                  {logs.length === 0 && phase === "running" && (
                    <p className="text-muted-foreground">Waiting for events…</p>
                  )}
                  {logs.map((log, i) => (
                    <div key={i} className="py-0.5 text-muted-foreground">
                      <span className="text-accent">
                        [{log.payload.step ?? log.type}]
                      </span>{" "}
                      {log.payload.message ?? log.payload.error ?? log.type}
                    </div>
                  ))}
                  <div ref={logsEndRef} />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-border px-4 py-3">
          {phase === "form" && (
            <>
              <Button variant="outline" size="sm" onClick={onClose}>
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleRun}
                disabled={backfillMutation.isPending}
              >
                {backfillMutation.isPending ? (
                  <Loader2 size={14} className="mr-2 animate-spin" />
                ) : (
                  <RefreshCw size={14} className="mr-2" />
                )}
                Run Backfill
              </Button>
            </>
          )}
          {phase === "running" && (
            <Button variant="outline" size="sm" disabled>
              <Loader2 size={14} className="mr-2 animate-spin" />
              Running…
            </Button>
          )}
          {(phase === "completed" || phase === "failed") && (
            <Button size="sm" onClick={onClose}>
              Close
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
