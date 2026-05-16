import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../client";

export interface OperatorActionRow {
  action_id: string;
  action_type: string;
  operator: string;
  performed_at: string;
  input_params: Record<string, unknown> | null;
  result_summary: string | null;
  request_id: string | null;
}

export interface OperatorActionsResponse {
  actions: OperatorActionRow[];
  total: number;
}

export interface ModelVersionRow {
  model_version: string;
  first_seen: string;
  last_seen: string;
  prediction_count: number;
}

export interface ModelVersionsResponse {
  versions: ModelVersionRow[];
}

export interface DecisionRow {
  bet_id: string;
  fixture_id: string;
  decided_at: string;
  market: string;
  selection: string;
  stake_gbp: string;
  odds: string;
  edge_pct: number;
  settlement_status: string;
  prediction_id: string | null;
}

export interface DecisionsResponse {
  decisions: DecisionRow[];
  total: number;
}

export function useOperatorActions(opts?: {
  action_type?: string;
  since?: string;
  limit?: number;
  offset?: number;
}) {
  const params: Record<string, string> = {};
  if (opts?.action_type) params.action_type = opts.action_type;
  if (opts?.since) params.since = opts.since;
  if (opts?.limit !== undefined) params.limit = String(opts.limit);
  if (opts?.offset !== undefined) params.offset = String(opts.offset);
  return useQuery({
    queryKey: ["audit", "operator-actions", opts],
    queryFn: () =>
      apiClient.get<OperatorActionsResponse>("/api/v1/audit/operator-actions", params),
    staleTime: 10_000,
  });
}

export function useModelVersions() {
  return useQuery({
    queryKey: ["audit", "model-versions"],
    queryFn: () =>
      apiClient.get<ModelVersionsResponse>("/api/v1/audit/model-versions"),
    staleTime: 30_000,
  });
}

export function useDecisions(opts?: {
  since?: string;
  limit?: number;
  offset?: number;
}) {
  const params: Record<string, string> = {};
  if (opts?.since) params.since = opts.since;
  if (opts?.limit !== undefined) params.limit = String(opts.limit);
  if (opts?.offset !== undefined) params.offset = String(opts.offset);
  return useQuery({
    queryKey: ["audit", "decisions", opts],
    queryFn: () =>
      apiClient.get<DecisionsResponse>("/api/v1/audit/decisions", params),
    staleTime: 10_000,
  });
}
