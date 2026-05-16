"use client";

import { useState } from "react";
import { RefreshCw, Loader2, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useOperatorActions,
  useModelVersions,
  useDecisions,
} from "@/lib/api/hooks";
import type { OperatorActionRow, DecisionRow } from "@/lib/api/hooks";

const ACTION_TYPES = [
  "ALL",
  "pipeline_cycle",
  "pipeline_loop_start",
  "pipeline_loop_stop",
  "bootstrap_run",
  "alias_create",
  "alias_retire",
  "prediction_run",
  "clv_backfill",
  "circuit_breaker_reset",
];

function formatTs(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function ActionRow({ action }: { action: OperatorActionRow }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <>
      <tr
        className="border-b last:border-0 hover:bg-muted/30 cursor-pointer"
        onClick={() => setExpanded((e) => !e)}
      >
        <td className="py-1.5 pr-3 font-mono text-xs text-muted-foreground whitespace-nowrap">
          {formatTs(action.performed_at)}
        </td>
        <td className="py-1.5 pr-3">
          <Badge variant="outline" className="text-xs font-mono">
            {action.action_type}
          </Badge>
        </td>
        <td className="py-1.5 pr-3 text-xs">{action.operator}</td>
        <td className="py-1.5 text-xs text-muted-foreground">
          {action.result_summary ?? "—"}
        </td>
        <td className="py-1.5 pl-2">
          {expanded ? (
            <ChevronUp className="h-3 w-3" />
          ) : (
            <ChevronDown className="h-3 w-3" />
          )}
        </td>
      </tr>
      {expanded && action.input_params && (
        <tr className="border-b bg-muted/20">
          <td colSpan={5} className="px-3 py-2">
            <pre className="text-xs font-mono overflow-x-auto whitespace-pre-wrap">
              {JSON.stringify(action.input_params, null, 2)}
            </pre>
          </td>
        </tr>
      )}
    </>
  );
}

function DecisionRowComp({ decision }: { decision: DecisionRow }) {
  const settlementColor =
    decision.settlement_status === "won"
      ? "text-green-600"
      : decision.settlement_status === "lost"
        ? "text-destructive"
        : "text-muted-foreground";
  return (
    <tr className="border-b last:border-0">
      <td className="py-1.5 pr-3 font-mono text-xs text-muted-foreground whitespace-nowrap">
        {formatTs(decision.decided_at)}
      </td>
      <td className="py-1.5 pr-3 font-mono text-xs max-w-[160px] truncate">
        {decision.fixture_id}
      </td>
      <td className="py-1.5 pr-3 text-xs">{decision.market}</td>
      <td className="py-1.5 pr-3 text-xs font-medium">{decision.selection}</td>
      <td className="py-1.5 pr-3 text-xs">£{decision.stake_gbp}</td>
      <td className="py-1.5 pr-3 text-xs">{decision.odds}</td>
      <td className="py-1.5 pr-3 text-xs text-green-600">
        {(decision.edge_pct * 100).toFixed(1)}%
      </td>
      <td className={`py-1.5 text-xs font-medium ${settlementColor}`}>
        {decision.settlement_status}
      </td>
    </tr>
  );
}

export default function AuditPage() {
  const [actionTypeFilter, setActionTypeFilter] = useState("ALL");

  const {
    data: actionsData,
    isLoading: actionsLoading,
    refetch: refetchActions,
    isFetching: actionsFetching,
  } = useOperatorActions({
    action_type: actionTypeFilter === "ALL" ? undefined : actionTypeFilter,
    limit: 50,
  });

  const { data: versions, isLoading: versionsLoading } = useModelVersions();
  const { data: decisions, isLoading: decisionsLoading } = useDecisions({ limit: 50 });

  return (
    <div className="flex flex-col gap-6 p-6">
      <h1 className="text-2xl font-bold">Audit Trail</h1>

      {/* Operator Actions */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">
            Operator Actions
            {actionsData ? (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                ({actionsData.total} total)
              </span>
            ) : null}
          </CardTitle>
          <div className="flex items-center gap-2">
            <select
              className="h-8 rounded-md border bg-background px-2 text-xs"
              value={actionTypeFilter}
              onChange={(e) => setActionTypeFilter(e.target.value)}
            >
              {ACTION_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void refetchActions()}
              disabled={actionsFetching}
            >
              <RefreshCw
                className={`h-4 w-4 ${actionsFetching ? "animate-spin" : ""}`}
              />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {actionsLoading ? (
            <div className="flex items-center gap-2 text-muted-foreground py-6 justify-center">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : (actionsData?.actions ?? []).length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No operator actions recorded yet.
            </p>
          ) : (
            <div className="overflow-x-auto max-h-80 overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-card">
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-1 font-medium pr-3">When</th>
                    <th className="pb-1 font-medium pr-3">Action</th>
                    <th className="pb-1 font-medium pr-3">Operator</th>
                    <th className="pb-1 font-medium">Result</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {(actionsData?.actions ?? []).map((a) => (
                    <ActionRow key={a.action_id} action={a} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Model Versions */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Model Versions</CardTitle>
        </CardHeader>
        <CardContent>
          {versionsLoading ? (
            <div className="flex items-center gap-2 text-muted-foreground py-6 justify-center">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : (versions?.versions ?? []).length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No model versions logged yet.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="pb-1 font-medium pr-3">Version</th>
                  <th className="pb-1 font-medium pr-3">First Seen</th>
                  <th className="pb-1 font-medium pr-3">Last Seen</th>
                  <th className="pb-1 font-medium">Predictions</th>
                </tr>
              </thead>
              <tbody>
                {(versions?.versions ?? []).map((v) => (
                  <tr key={v.model_version} className="border-b last:border-0">
                    <td className="py-1.5 pr-3 font-mono text-xs font-medium">
                      {v.model_version}
                    </td>
                    <td className="py-1.5 pr-3 text-xs text-muted-foreground">
                      {formatTs(v.first_seen)}
                    </td>
                    <td className="py-1.5 pr-3 text-xs text-muted-foreground">
                      {formatTs(v.last_seen)}
                    </td>
                    <td className="py-1.5 text-xs font-semibold">
                      {v.prediction_count.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {/* Bet Decisions */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">
            Bet Decisions
            {decisions ? (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                ({decisions.total} total)
              </span>
            ) : null}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {decisionsLoading ? (
            <div className="flex items-center gap-2 text-muted-foreground py-6 justify-center">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : (decisions?.decisions ?? []).length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No bet decisions recorded yet.
            </p>
          ) : (
            <div className="overflow-x-auto max-h-96 overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-card">
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-1 font-medium pr-3">When</th>
                    <th className="pb-1 font-medium pr-3">Fixture</th>
                    <th className="pb-1 font-medium pr-3">Market</th>
                    <th className="pb-1 font-medium pr-3">Selection</th>
                    <th className="pb-1 font-medium pr-3">Stake</th>
                    <th className="pb-1 font-medium pr-3">Odds</th>
                    <th className="pb-1 font-medium pr-3">Edge</th>
                    <th className="pb-1 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(decisions?.decisions ?? []).map((d) => (
                    <DecisionRowComp key={d.bet_id} decision={d} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
