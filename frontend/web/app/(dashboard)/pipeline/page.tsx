"use client";

import { useState, useCallback } from "react";
import {
  Activity,
  CheckCircle2,
  Circle,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  usePipelineStatus,
  usePipelineJobs,
  useStartCycle,
  useStartLoop,
  useStopLoop,
} from "@/lib/api/hooks";
import type { FreshnessEntry, JobResponse } from "@/lib/api/hooks";
import { useWebSocket } from "@/lib/api/ws";
import { CircuitBreakerLED } from "@/components/layout/circuit-breaker-led";

interface WsEvent {
  type: string;
  timestamp: string;
  payload?: Record<string, unknown>;
}

const PIPELINE_NODES = [
  "scraper",
  "news",
  "analyst",
  "pricing",
  "risk",
  "execution",
];

export default function PipelinePage() {
  const { data: status } = usePipelineStatus();
  const { data: jobsData } = usePipelineJobs({ limit: 20 });
  const startCycle = useStartCycle();
  const startLoop = useStartLoop();
  const stopLoop = useStopLoop();

  const [intervalMin, setIntervalMin] = useState(15);
  const [nodeStates, setNodeStates] = useState<
    Record<string, "pending" | "running" | "complete" | "failed">
  >({});
  const [cycleActive, setCycleActive] = useState(false);
  const [expandedJob, setExpandedJob] = useState<string | null>(null);

  const handleWsMessage = useCallback((event: WsEvent) => {
    if (event.type === "cycle_started") {
      setCycleActive(true);
      setNodeStates({});
    } else if (event.type === "node_started") {
      const node = event.payload?.node as string;
      if (node) setNodeStates((s) => ({ ...s, [node]: "running" }));
    } else if (event.type === "node_complete") {
      const node = event.payload?.node as string;
      if (node) setNodeStates((s) => ({ ...s, [node]: "complete" }));
    } else if (event.type === "cycle_finished") {
      setCycleActive(false);
      toast.success("Pipeline cycle completed");
    } else if (event.type === "cycle_failed") {
      setCycleActive(false);
      toast.error(`Pipeline cycle failed: ${event.payload?.error ?? "unknown"}`);
    }
  }, []);

  useWebSocket<WsEvent>("/ws/v1/pipeline", {
    enabled: true,
    onMessage: handleWsMessage,
  });

  const [freshness, setFreshness] = useState<Record<string, FreshnessEntry>>(
    {},
  );
  useWebSocket<{ payload: Record<string, FreshnessEntry> }>(
    "/ws/v1/freshness",
    {
      enabled: true,
      onMessage: (msg) => {
        if (msg.payload) setFreshness(msg.payload);
      },
    },
  );

  function handleRunCycle() {
    startCycle.mutate(undefined, {
      onSuccess: () => toast.success("Cycle started"),
      onError: (e) => toast.error(e.message),
    });
  }

  function handleToggleLoop() {
    if (status?.loop.active) {
      stopLoop.mutate(undefined, {
        onSuccess: () => toast.success("Loop stopped"),
        onError: (e) => toast.error(e.message),
      });
    } else {
      startLoop.mutate(intervalMin, {
        onSuccess: () => toast.success(`Loop started · every ${intervalMin}m`),
        onError: (e) => toast.error(e.message),
      });
    }
  }

  const loopActive = status?.loop.active ?? false;

  return (
    <div className="space-y-6">
      {/* Status bar */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-card p-4">
        <div className="flex items-center gap-2 text-sm">
          <Activity size={14} />
          <span className="text-muted-foreground">Last cycle:</span>
          <span className="font-mono">
            {status?.last_cycle_at
              ? new Date(status.last_cycle_at).toLocaleString()
              : "never"}
          </span>
          {status?.last_cycle_duration_s != null && (
            <span className="text-muted-foreground">
              ({status.last_cycle_duration_s}s)
            </span>
          )}
        </div>
        <CircuitBreakerLED breaker={status?.circuit_breaker ?? null} />
        <span
          className={`rounded-full px-3 py-1 font-mono text-xs font-medium ${
            loopActive
              ? "bg-success/20 text-success"
              : "bg-muted text-muted-foreground"
          }`}
        >
          {loopActive
            ? `RUNNING · every ${status?.loop.interval_min ?? "?"}m`
            : "IDLE"}
        </span>
      </div>

      {/* Action bar */}
      <div className="flex flex-wrap items-center gap-3">
        <Button
          onClick={handleRunCycle}
          disabled={cycleActive || startCycle.isPending}
          className="bg-accent text-accent-foreground hover:bg-accent/90"
        >
          {cycleActive || startCycle.isPending ? (
            <Loader2 size={16} className="mr-2 animate-spin" />
          ) : (
            <RefreshCw size={16} className="mr-2" />
          )}
          Run Cycle
        </Button>

        <div className="flex items-center gap-2">
          <Input
            type="number"
            min={1}
            max={1440}
            value={intervalMin}
            onChange={(e) => setIntervalMin(Number(e.target.value))}
            className="w-20"
            disabled={loopActive}
          />
          <span className="text-sm text-muted-foreground">min</span>
        </div>

        <Button
          variant={loopActive ? "destructive" : "outline"}
          onClick={handleToggleLoop}
          disabled={startLoop.isPending || stopLoop.isPending}
        >
          {loopActive ? (
            <>
              <Pause size={16} className="mr-2" />
              Stop Loop
            </>
          ) : (
            <>
              <Play size={16} className="mr-2" />
              Start Loop
            </>
          )}
        </Button>
      </div>

      {/* Progress panel */}
      {cycleActive && (
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="mb-3 text-sm font-semibold">Cycle Progress</h3>
          <div className="space-y-2">
            {PIPELINE_NODES.map((node) => {
              const state = nodeStates[node] ?? "pending";
              return (
                <div key={node} className="flex items-center gap-3 text-sm">
                  {state === "pending" && (
                    <Circle size={16} className="text-muted-foreground" />
                  )}
                  {state === "running" && (
                    <Loader2
                      size={16}
                      className="animate-spin text-accent"
                    />
                  )}
                  {state === "complete" && (
                    <CheckCircle2 size={16} className="text-success" />
                  )}
                  {state === "failed" && (
                    <XCircle size={16} className="text-destructive" />
                  )}
                  <span
                    className={
                      state === "running"
                        ? "font-medium text-foreground"
                        : "text-muted-foreground"
                    }
                  >
                    {node}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Freshness panel */}
      <div className="rounded-lg border border-border bg-card p-4">
        <h3 className="mb-3 text-sm font-semibold">Data Freshness</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(
            Object.keys(freshness).length > 0
              ? freshness
              : status?.freshness ?? {},
          ).map(([key, entry]) => {
            const e = entry as FreshnessEntry;
            const color =
              e.status === "ok"
                ? "bg-success"
                : e.status === "warning"
                  ? "bg-yellow-500"
                  : "bg-destructive";
            return (
              <div
                key={key}
                className="flex items-center gap-3 rounded-md border border-border px-3 py-2"
              >
                <div className={`h-2 w-2 rounded-full ${color}`} />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-xs font-medium">
                    {e.source}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {e.age_seconds != null
                      ? `${e.age_seconds}s ago`
                      : "no data"}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Cycle history table */}
      <div className="rounded-lg border border-border bg-card p-4">
        <h3 className="mb-3 text-sm font-semibold">Cycle History</h3>
        {jobsData?.jobs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No cycles yet</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="pb-2 pr-4 font-medium">Job ID</th>
                  <th className="pb-2 pr-4 font-medium">Started</th>
                  <th className="pb-2 pr-4 font-medium">Duration</th>
                  <th className="pb-2 pr-4 font-medium">Status</th>
                  <th className="pb-2 font-medium">Error</th>
                </tr>
              </thead>
              <tbody>
                {jobsData?.jobs.map((job: JobResponse) => (
                  <tr
                    key={job.job_id}
                    className="cursor-pointer border-b border-border/50 hover:bg-muted/50"
                    onClick={() =>
                      setExpandedJob(
                        expandedJob === job.job_id ? null : job.job_id,
                      )
                    }
                  >
                    <td className="py-2 pr-4 font-mono text-xs">
                      {job.job_id}
                    </td>
                    <td className="py-2 pr-4">
                      {job.started_at
                        ? new Date(job.started_at).toLocaleTimeString()
                        : "-"}
                    </td>
                    <td className="py-2 pr-4 font-mono">
                      {job.duration_s != null ? `${job.duration_s}s` : "-"}
                    </td>
                    <td className="py-2 pr-4">
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="max-w-[200px] truncate py-2 text-destructive">
                      {job.error ?? ""}
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

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    queued: "bg-muted text-muted-foreground",
    running: "bg-accent/20 text-accent",
    completed: "bg-success/20 text-success",
    failed: "bg-destructive/20 text-destructive",
  };
  return (
    <span
      className={`rounded-full px-2 py-0.5 font-mono text-xs ${styles[status] ?? styles.queued}`}
    >
      {status}
    </span>
  );
}
