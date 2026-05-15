import { useMutation, useQuery } from "@tanstack/react-query";
import { apiClient } from "../client";

export interface ExposureFixture {
  fixture_id: string;
  open_stake: string;
}

export interface ExposureResponse {
  today_open: string;
  total_open: string;
  per_fixture: ExposureFixture[];
}

export interface BankrollPoint {
  decided_at: string;
  bankroll: string;
}

export interface BankrollResponse {
  current: string;
  peak: string;
  drawdown_pct: number;
  sparkline: BankrollPoint[];
}

export interface KellyPreviewRequest {
  p_hat: number;
  sigma_p: number;
  odds: number;
  base_fraction: number;
  uncertainty_k: number;
  per_bet_cap_pct: number;
  recent_clv_pct: number;
  bankroll: string;
}

export interface KellyPreviewResponse {
  stake: string;
  f_full: number;
  f_used: number;
  p_lb: number;
  clv_multiplier: number;
  per_bet_cap_hit: boolean;
}

export function useExposure() {
  return useQuery({
    queryKey: ["risk", "exposure"],
    queryFn: () => apiClient.get<ExposureResponse>("/api/v1/risk/exposure"),
    staleTime: 30_000,
  });
}

export function useBankroll() {
  return useQuery({
    queryKey: ["risk", "bankroll"],
    queryFn: () => apiClient.get<BankrollResponse>("/api/v1/risk/bankroll"),
    staleTime: 30_000,
  });
}

export function useKellyPreview() {
  return useMutation({
    mutationFn: (body: KellyPreviewRequest) =>
      apiClient.post<KellyPreviewResponse>("/api/v1/risk/kelly-preview", body),
  });
}
