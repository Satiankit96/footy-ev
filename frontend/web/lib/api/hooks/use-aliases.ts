import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../client";

export interface AliasResponse {
  event_ticker: string;
  fixture_id: string;
  confidence: number;
  resolved_by: string;
  resolved_at: string | null;
  status: string;
}

export interface AliasListResponse {
  aliases: AliasResponse[];
  total: number;
}

export interface AliasConflict {
  fixture_id: string;
  alias_count: number;
  tickers: string[];
}

export interface AliasConflictsResponse {
  conflicts: AliasConflict[];
}

export interface AliasCreateRequest {
  event_ticker: string;
  fixture_id: string;
  confidence?: number;
  resolved_by?: string;
}

export interface AliasRetireResponse {
  event_ticker: string;
  status: string;
  retired_at: string;
}

export function useAliases(params?: {
  status?: string;
  limit?: number;
  offset?: number;
}) {
  const qs: Record<string, string> = {};
  if (params?.status && params.status !== "all") qs.status = params.status;
  if (params?.limit) qs.limit = String(params.limit);
  if (params?.offset) qs.offset = String(params.offset);

  return useQuery({
    queryKey: ["aliases", params],
    queryFn: () => apiClient.get<AliasListResponse>("/api/v1/aliases", qs),
    staleTime: 30_000,
  });
}

export function useAlias(eventTicker: string | null) {
  return useQuery({
    queryKey: ["aliases", eventTicker],
    queryFn: () =>
      apiClient.get<AliasResponse>(`/api/v1/aliases/${eventTicker}`),
    enabled: !!eventTicker,
  });
}

export function useAliasConflicts() {
  return useQuery({
    queryKey: ["aliases", "conflicts"],
    queryFn: () =>
      apiClient.get<AliasConflictsResponse>("/api/v1/aliases/conflicts"),
    staleTime: 60_000,
  });
}

export function useCreateAlias() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AliasCreateRequest) =>
      apiClient.post<AliasResponse>("/api/v1/aliases", body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["aliases"] });
    },
  });
}

export function useRetireAlias() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (eventTicker: string) =>
      apiClient.post<AliasRetireResponse>(
        `/api/v1/aliases/${eventTicker}/retire`,
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["aliases"] });
    },
  });
}
