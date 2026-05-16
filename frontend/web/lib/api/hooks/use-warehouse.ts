import { useMutation, useQuery } from "@tanstack/react-query";
import { apiClient } from "../client";

export interface TableInfo {
  name: string;
  row_count: number;
  last_write: string | null;
}

export interface TableListResponse {
  tables: TableInfo[];
}

export interface TeamRow {
  team_id: string;
  name: string | null;
  league: string | null;
  fixture_count: number;
}

export interface TeamListResponse {
  teams: TeamRow[];
  total: number;
}

export interface FormResult {
  fixture_id: string;
  date: string | null;
  opponent_id: string;
  home_away: string;
  score: string | null;
  result: string | null;
  home_xg: string | null;
  away_xg: string | null;
}

export interface TeamDetailResponse {
  team_id: string;
  name: string | null;
  league: string | null;
  form: FormResult[];
}

export interface PlayerListResponse {
  players: unknown[];
  note: string;
}

export interface SnapshotRow {
  fixture_id: string;
  venue: string;
  market: string;
  selection: string;
  odds_decimal: number | null;
  received_at: string | null;
}

export interface SnapshotListResponse {
  snapshots: SnapshotRow[];
  total: number;
}

export interface CannedQueryRequest {
  query_name: string;
  params: Record<string, unknown>;
}

export interface CannedQueryResponse {
  query_name: string;
  columns: string[];
  rows: unknown[][];
  row_count: number;
}

export function useWarehouseTables() {
  return useQuery({
    queryKey: ["warehouse", "tables"],
    queryFn: () => apiClient.get<TableListResponse>("/api/v1/warehouse/tables"),
    staleTime: 60_000,
  });
}

export function useWarehouseTeams(league?: string) {
  const params: Record<string, string> = {};
  if (league) params.league = league;
  return useQuery({
    queryKey: ["warehouse", "teams", league ?? "all"],
    queryFn: () => apiClient.get<TeamListResponse>("/api/v1/warehouse/teams", params),
    staleTime: 60_000,
  });
}

export function useWarehouseTeam(teamId: string) {
  return useQuery({
    queryKey: ["warehouse", "teams", teamId],
    queryFn: () => apiClient.get<TeamDetailResponse>(`/api/v1/warehouse/teams/${teamId}`),
    staleTime: 60_000,
    enabled: !!teamId,
  });
}

export function useWarehousePlayers(opts?: {
  team_id?: string;
  limit?: number;
  offset?: number;
}) {
  const params: Record<string, string> = {};
  if (opts?.team_id) params.team_id = opts.team_id;
  if (opts?.limit !== undefined) params.limit = String(opts.limit);
  if (opts?.offset !== undefined) params.offset = String(opts.offset);
  return useQuery({
    queryKey: ["warehouse", "players", opts],
    queryFn: () => apiClient.get<PlayerListResponse>("/api/v1/warehouse/players", params),
    staleTime: 60_000,
  });
}

export function useWarehouseSnapshots(opts?: {
  fixture_id?: string;
  market?: string;
  venue?: string;
  limit?: number;
  offset?: number;
}) {
  const params: Record<string, string> = {};
  if (opts?.fixture_id) params.fixture_id = opts.fixture_id;
  if (opts?.market) params.market = opts.market;
  if (opts?.venue) params.venue = opts.venue;
  if (opts?.limit !== undefined) params.limit = String(opts.limit);
  if (opts?.offset !== undefined) params.offset = String(opts.offset);
  return useQuery({
    queryKey: ["warehouse", "snapshots", opts],
    queryFn: () =>
      apiClient.get<SnapshotListResponse>("/api/v1/warehouse/odds-snapshots", params),
    staleTime: 30_000,
  });
}

export function useWarehouseQueryNames() {
  return useQuery({
    queryKey: ["warehouse", "query-names"],
    queryFn: () => apiClient.get<string[]>("/api/v1/warehouse/query/names"),
    staleTime: Infinity,
  });
}

export function useWarehouseQuery() {
  return useMutation({
    mutationFn: (body: CannedQueryRequest) =>
      apiClient.post<CannedQueryResponse>("/api/v1/warehouse/query", body),
  });
}
