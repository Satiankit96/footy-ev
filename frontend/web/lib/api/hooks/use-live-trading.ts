import { useMutation, useQuery } from "@tanstack/react-query";
import { apiClient } from "../client";

export interface LiveTradingStatus {
  enabled: boolean;
  gate_reasons: string[];
}

export interface ClvConditionResult {
  met: boolean;
  bet_count: number;
  days_span: number;
  mean_clv_pct: number;
}

export interface BankrollConditionResult {
  met: boolean;
  flag_name: string;
  flag_set: boolean;
}

export interface ConditionsResponse {
  clv_condition: ClvConditionResult;
  bankroll_condition: BankrollConditionResult;
  all_met: boolean;
}

export function useLiveTradingStatus() {
  return useQuery({
    queryKey: ["live-trading", "status"],
    queryFn: () => apiClient.get<LiveTradingStatus>("/api/v1/live-trading/status"),
    staleTime: 30_000,
  });
}

export function useCheckConditions() {
  return useMutation({
    mutationFn: () =>
      apiClient.post<ConditionsResponse>("/api/v1/live-trading/check-conditions"),
  });
}
