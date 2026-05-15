import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../client";

export interface KalshiCredentialsResponse {
  configured: boolean;
  key_id_present: boolean;
  private_key_present: boolean;
  base_url: string;
  is_demo: boolean;
}

export interface KalshiHealthResponse {
  ok: boolean;
  latency_ms: number | null;
  clock_skew_s: number | null;
  base_url: string;
  error: string | null;
}

export interface KalshiEventResponse {
  event_ticker: string;
  series_ticker: string;
  title: string;
  sub_title: string | null;
  category: string | null;
  alias_status: string | null;
  fixture_id: string | null;
}

export interface KalshiEventListResponse {
  events: KalshiEventResponse[];
  total: number;
}

export interface KalshiMarketResponse {
  ticker: string;
  event_ticker: string;
  floor_strike: string;
  yes_bid: string;
  no_bid: string;
  yes_ask: string | null;
  no_ask: string | null;
  yes_bid_size: number | null;
  yes_ask_size: number | null;
  decimal_odds: string | null;
  implied_probability: string | null;
}

export interface KalshiEventDetailResponse {
  event: KalshiEventResponse;
  markets: KalshiMarketResponse[];
}

export interface KalshiMarketDetailResponse {
  market: KalshiMarketResponse;
  recent_snapshots: Record<string, unknown>[];
}

export function useKalshiCredentials() {
  return useQuery({
    queryKey: ["kalshi", "credentials"],
    queryFn: () =>
      apiClient.get<KalshiCredentialsResponse>(
        "/api/v1/kalshi/credentials/status",
      ),
    staleTime: 60_000,
  });
}

export function useKalshiHealthCheck() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiClient.get<KalshiHealthResponse>("/api/v1/kalshi/health"),
    onSuccess: (data) => {
      qc.setQueryData(["kalshi", "health"], data);
    },
  });
}

export function useKalshiHealth() {
  return useQuery({
    queryKey: ["kalshi", "health"],
    queryFn: () =>
      apiClient.get<KalshiHealthResponse>("/api/v1/kalshi/health"),
    enabled: false,
  });
}

export function useKalshiEvents(params?: {
  series?: string;
  status?: string;
  limit?: number;
}) {
  const qs: Record<string, string> = {};
  if (params?.series) qs.series = params.series;
  if (params?.status) qs.status = params.status;
  if (params?.limit) qs.limit = String(params.limit);

  return useQuery({
    queryKey: ["kalshi", "events", params],
    queryFn: () =>
      apiClient.get<KalshiEventListResponse>("/api/v1/kalshi/events", qs),
    enabled: false,
  });
}

export function useKalshiEventDetail(ticker: string | null) {
  return useQuery({
    queryKey: ["kalshi", "events", ticker],
    queryFn: () =>
      apiClient.get<KalshiEventDetailResponse>(
        `/api/v1/kalshi/events/${ticker}`,
      ),
    enabled: !!ticker,
  });
}

export function useKalshiMarketDetail(ticker: string | null) {
  return useQuery({
    queryKey: ["kalshi", "markets", ticker],
    queryFn: () =>
      apiClient.get<KalshiMarketDetailResponse>(
        `/api/v1/kalshi/markets/${ticker}`,
      ),
    enabled: !!ticker,
  });
}
