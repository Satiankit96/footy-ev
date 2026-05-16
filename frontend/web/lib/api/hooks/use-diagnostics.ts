import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../client";

export interface CircuitBreakerState {
  state: string;
  last_tripped_at: string | null;
  reason: string | null;
}

export interface MigrationInfo {
  name: string;
  applied: boolean;
  applied_at: string | null;
}

export interface MigrationListResponse {
  migrations: MigrationInfo[];
}

export interface EnvVarInfo {
  name: string;
  is_set: boolean;
  required: boolean;
}

export interface EnvCheckResponse {
  vars: EnvVarInfo[];
}

export interface LogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
}

export interface LogsResponse {
  entries: LogEntry[];
  total: number;
}

export function useCircuitBreaker() {
  return useQuery({
    queryKey: ["diagnostics", "circuit-breaker"],
    queryFn: () =>
      apiClient.get<CircuitBreakerState>("/api/v1/diagnostics/circuit-breaker"),
    staleTime: 10_000,
  });
}

export function useResetCircuitBreaker() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiClient.post<CircuitBreakerState>("/api/v1/diagnostics/circuit-breaker/reset"),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["diagnostics", "circuit-breaker"] });
    },
  });
}

export function useDiagnosticsLogs(opts?: {
  level?: string;
  since?: string;
  limit?: number;
}) {
  const params: Record<string, string> = {};
  if (opts?.level) params.level = opts.level;
  if (opts?.since) params.since = opts.since;
  if (opts?.limit !== undefined) params.limit = String(opts.limit);
  return useQuery({
    queryKey: ["diagnostics", "logs", opts],
    queryFn: () => apiClient.get<LogsResponse>("/api/v1/diagnostics/logs", params),
    staleTime: 5_000,
  });
}

export function useDiagnosticsMigrations() {
  return useQuery({
    queryKey: ["diagnostics", "migrations"],
    queryFn: () =>
      apiClient.get<MigrationListResponse>("/api/v1/diagnostics/migrations"),
    staleTime: 60_000,
  });
}

export function useDiagnosticsEnv() {
  return useQuery({
    queryKey: ["diagnostics", "env"],
    queryFn: () => apiClient.get<EnvCheckResponse>("/api/v1/diagnostics/env"),
    staleTime: 30_000,
  });
}
