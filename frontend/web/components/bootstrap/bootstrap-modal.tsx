"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  CheckCircle2,
  Loader2,
  Play,
  X,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  useBootstrapPreview,
  useBootstrapRun,
  useBootstrapJob,
} from "@/lib/api/hooks";
import type { BootstrapPreviewResponse } from "@/lib/api/hooks";
import { useWebSocket } from "@/lib/api/ws";

interface ProgressEvent {
  type: string;
  timestamp?: string;
  payload: {
    job_id: string;
    step?: string;
    message?: string;
    percent?: number;
    status?: string;
    error?: string;
    auto_resolved_count?: number;
    fixture_auto_created_count?: number;
    needs_review_count?: number;
    error_count?: number;
  };
}

type Phase = "preview" | "running" | "completed" | "failed";

export function BootstrapModal({ onClose }: { onClose: () => void }) {
  const [phase, setPhase] = useState<Phase>("preview");
  const [jobId, setJobId] = useState<string | null>(null);
  const [logs, setLogs] = useState<ProgressEvent[]>([]);
  const [percent, setPercent] = useState(0);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const {
    data: preview,
    refetch: fetchPreview,
    isFetching: previewLoading,
  } = useBootstrapPreview();
  const runMutation = useBootstrapRun();
  const { data: jobData } = useBootstrapJob(
    phase === "running" ? jobId : null,
  );

  const handleWsMessage = useCallback((event: ProgressEvent) => {
    setLogs((prev) => [...prev, event]);
    if (event.payload.percent) {
      setPercent(event.payload.percent);
    }
    if (event.type === "completed") {
      setPhase("completed");
    } else if (event.type === "failed") {
      setPhase("failed");
    }
  }, []);

  useWebSocket<ProgressEvent>(
    jobId ? `/ws/v1/jobs/${jobId}` : "",
    {
      enabled: !!jobId && phase === "running",
      onMessage: handleWsMessage,
    },
  );

  useEffect(() => {
    void fetchPreview();
  }, [fetchPreview]);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const effectivePhase =
    phase === "running" && jobData
      ? jobData.status === "completed"
        ? "completed"
        : jobData.status === "failed"
          ? "failed"
          : phase
      : phase;

  function handleRun() {
    runMutation.mutate(
      { mode: "live", create_fixtures: true },
      {
        onSuccess: (data) => {
          setJobId(data.job_id);
          setPhase("running");
          setLogs([]);
          setPercent(0);
        },
        onError: (e) => toast.error(e.message),
      },
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="flex w-full max-w-2xl flex-col rounded-lg border border-border bg-card shadow-lg">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-lg font-semibold">Bootstrap Kalshi Aliases</h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="max-h-[70vh] overflow-y-auto p-4 space-y-4">
          {/* Preview stats */}
          {effectivePhase === "preview" && (
            <>
              {previewLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2
                    size={24}
                    className="animate-spin text-muted-foreground"
                  />
                </div>
              ) : preview ? (
                <PreviewStats preview={preview} />
              ) : (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  Loading preview…
                </p>
              )}
            </>
          )}

          {/* Progress */}
          {(effectivePhase === "running" || effectivePhase === "completed" || effectivePhase === "failed") && (
            <>
              {/* Progress bar */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">
                    {effectivePhase === "running"
                      ? "Running…"
                      : effectivePhase === "completed"
                        ? "Completed"
                        : "Failed"}
                  </span>
                  <span className="font-mono">{percent}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className={`h-full transition-all duration-300 ${
                      effectivePhase === "failed" ? "bg-destructive" : "bg-accent"
                    }`}
                    style={{ width: `${percent}%` }}
                  />
                </div>
              </div>

              {/* Result summary */}
              {effectivePhase === "completed" && jobData && (
                <CompletedSummary progress={jobData.progress} />
              )}
              {effectivePhase === "failed" && jobData?.error && (
                <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                  {jobData.error}
                </div>
              )}

              {/* Log drawer */}
              <div className="rounded-md border border-border bg-muted/30 p-3">
                <p className="mb-2 text-xs font-medium text-muted-foreground">
                  Progress Log ({logs.length} events)
                </p>
                <div className="max-h-48 overflow-y-auto font-mono text-xs">
                  {logs.map((log, i) => (
                    <div key={i} className="py-0.5 text-muted-foreground">
                      <span className="text-accent">[{log.payload.step ?? log.type}]</span>{" "}
                      {log.payload.message ?? log.payload.error ?? log.type}
                    </div>
                  ))}
                  <div ref={logsEndRef} />
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-border px-4 py-3">
          {effectivePhase === "preview" && (
            <>
              <Button variant="outline" size="sm" onClick={onClose}>
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleRun}
                disabled={runMutation.isPending || previewLoading}
              >
                {runMutation.isPending ? (
                  <Loader2 size={14} className="mr-2 animate-spin" />
                ) : (
                  <Play size={14} className="mr-2" />
                )}
                Run Bootstrap
              </Button>
            </>
          )}
          {effectivePhase === "running" && (
            <Button variant="outline" size="sm" disabled>
              <Loader2 size={14} className="mr-2 animate-spin" />
              Running…
            </Button>
          )}
          {(effectivePhase === "completed" || effectivePhase === "failed") && (
            <Button size="sm" onClick={onClose}>
              Close
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function PreviewStats({ preview }: { preview: BootstrapPreviewResponse }) {
  const stats = [
    { label: "Total Events", value: preview.total_events },
    { label: "Already Mapped", value: preview.already_mapped },
    { label: "Would Resolve", value: preview.would_resolve },
    {
      label: "Would Create Fixture",
      value: preview.would_create_fixture,
    },
    { label: "Would Skip", value: preview.would_skip },
  ];

  return (
    <div>
      <p className="mb-3 text-sm text-muted-foreground">
        Preview of what bootstrap would do with current Kalshi events:
      </p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {stats.map((s) => (
          <div
            key={s.label}
            className="rounded-md border border-border/50 p-3 text-center"
          >
            <p className="text-xl font-semibold">{s.value}</p>
            <p className="text-xs text-muted-foreground">{s.label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function CompletedSummary({
  progress,
}: {
  progress: Record<string, unknown>[];
}) {
  const result = progress.find(
    (p) => (p as { type?: string }).type === "result",
  ) as { payload?: Record<string, unknown> } | undefined;

  if (!result?.payload) return null;

  const p = result.payload;
  const stats = [
    { label: "Auto-Resolved", value: p.auto_resolved_count, icon: CheckCircle2, color: "text-success" },
    { label: "Fixtures Created", value: p.fixture_auto_created_count, icon: CheckCircle2, color: "text-accent" },
    { label: "Needs Review", value: p.needs_review_count, icon: XCircle, color: "text-yellow-500" },
    { label: "Errors", value: p.error_count, icon: XCircle, color: "text-destructive" },
  ];

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {stats.map((s) => (
        <div
          key={s.label}
          className="flex items-center gap-2 rounded-md border border-border/50 p-3"
        >
          <s.icon size={16} className={s.color} />
          <div>
            <p className="text-lg font-semibold">{String(s.value ?? 0)}</p>
            <p className="text-xs text-muted-foreground">{s.label}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
