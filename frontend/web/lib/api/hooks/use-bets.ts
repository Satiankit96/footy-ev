import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../client";

export interface BetResponse {
  decision_id: string;
  fixture_id: string;
  market: string;
  selection: string;
  odds_at_decision: number;
  stake_gbp: string;
  edge_pct: number;
  kelly_fraction_used: number;
  settlement_status: string;
  clv_pct: number | null;
  decided_at: string | null;
  venue: string;
}

export interface BetListResponse {
  bets: BetResponse[];
  total: number;
}

export interface KellyBreakdown {
  p_hat: number;
  sigma_p: number;
  uncertainty_k: number;
  p_lb: number;
  b: number;
  q: number;
  f_full: number;
  base_fraction: number;
  per_bet_cap_pct: number;
  f_used: number;
  per_bet_cap_hit: boolean;
  bankroll_used: string;
}

export interface EdgeMath {
  p_calibrated: number;
  odds_decimal: number;
  commission: number;
  edge: number;
  edge_pct_stored: number;
}

export interface BetDetailResponse extends BetResponse {
  run_id: string | null;
  sigma_p: number | null;
  bankroll_used: string;
  features_hash: string;
  settled_at: string | null;
  pnl_gbp: string | null;
  closing_odds: number | null;
  kelly_breakdown: KellyBreakdown;
  edge_math: EdgeMath;
}

export interface BetsSummaryResponse {
  period: string;
  total_bets: number;
  wins: number;
  losses: number;
  pending: number;
  total_pnl: string;
  total_staked: string;
  roi: number;
  mean_clv: number | null;
  min_clv: number | null;
  max_clv: number | null;
}

export interface ClvRollingPoint {
  bet_index: number;
  decided_at: string;
  clv_pct: number;
  rolling_clv: number;
  cumulative_clv: number;
}

export function useBets(params?: {
  status?: string;
  fixture_id?: string;
  venue?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}) {
  const qs: Record<string, string> = {};
  if (params?.status) qs.status = params.status;
  if (params?.fixture_id) qs.fixture_id = params.fixture_id;
  if (params?.venue) qs.venue = params.venue;
  if (params?.date_from) qs.date_from = params.date_from;
  if (params?.date_to) qs.date_to = params.date_to;
  if (params?.limit) qs.limit = String(params.limit);
  if (params?.offset) qs.offset = String(params.offset);

  return useQuery({
    queryKey: ["bets", params],
    queryFn: () => apiClient.get<BetListResponse>("/api/v1/bets", qs),
    staleTime: 30_000,
  });
}

export function useBetDetail(decisionId: string | null) {
  return useQuery({
    queryKey: ["bets", decisionId],
    queryFn: () =>
      apiClient.get<BetDetailResponse>(
        `/api/v1/bets/${encodeURIComponent(decisionId!)}`,
      ),
    enabled: !!decisionId,
  });
}

export function useBetsSummary(period: "7d" | "30d" | "all" = "all") {
  return useQuery({
    queryKey: ["bets", "summary", period],
    queryFn: () =>
      apiClient.get<BetsSummaryResponse>("/api/v1/bets/summary", { period }),
    staleTime: 60_000,
  });
}

export function useBetsClvRolling(window: number = 100) {
  return useQuery({
    queryKey: ["bets", "clv", "rolling", window],
    queryFn: () =>
      apiClient.get<ClvRollingPoint[]>("/api/v1/bets/clv/rolling", {
        window: String(window),
      }),
    staleTime: 60_000,
  });
}

export interface ClvBreakdownItem {
  fixture_id: string;
  market: string;
  selection: string;
  mean_clv: number | null;
  n_bets: number;
  total_staked: string;
  total_pnl: string;
}

export interface ClvSourceItem {
  source: string;
  n_bets: number;
  mean_clv: number | null;
}

export interface ClvBackfillResponse {
  job_id: string;
  status: string;
}

export function useClvRolling(window: number = 100, since?: string) {
  const qs: Record<string, string> = { window: String(window) };
  if (since) qs.since = since;
  return useQuery({
    queryKey: ["clv", "rolling", window, since],
    queryFn: () => apiClient.get<ClvRollingPoint[]>("/api/v1/clv/rolling", qs),
    staleTime: 60_000,
  });
}

export function useClvBreakdown(fixtureId?: string) {
  const qs: Record<string, string> = {};
  if (fixtureId) qs.fixture_id = fixtureId;
  return useQuery({
    queryKey: ["clv", "breakdown", fixtureId],
    queryFn: () =>
      apiClient.get<ClvBreakdownItem[]>("/api/v1/clv/breakdown", qs),
    staleTime: 60_000,
  });
}

export function useClvSources() {
  return useQuery({
    queryKey: ["clv", "sources"],
    queryFn: () => apiClient.get<ClvSourceItem[]>("/api/v1/clv/sources"),
    staleTime: 60_000,
  });
}

export function useClvBackfill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { from_date?: string; to_date?: string }) =>
      apiClient.post<ClvBackfillResponse>("/api/v1/clv/backfill", body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["clv"] });
      void qc.invalidateQueries({ queryKey: ["bets"] });
    },
  });
}
