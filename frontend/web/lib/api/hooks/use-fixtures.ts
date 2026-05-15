import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../client";

export interface FixtureAliasInfo {
  event_ticker: string;
  confidence: number;
  resolved_by: string;
  resolved_at: string | null;
}

export interface FixtureResponse {
  fixture_id: string;
  league: string;
  season: string;
  home_team_id: string | null;
  away_team_id: string | null;
  home_team_raw: string | null;
  away_team_raw: string | null;
  match_date: string | null;
  kickoff_utc: string | null;
  home_score_ft: number | null;
  away_score_ft: number | null;
  result_ft: string | null;
  home_xg: string | null;
  away_xg: string | null;
  status: string;
  alias_count: number;
}

export interface FixtureDetailResponse extends FixtureResponse {
  aliases: FixtureAliasInfo[];
  prediction_count: number;
  bet_count: number;
}

export interface FixtureListResponse {
  fixtures: FixtureResponse[];
  total: number;
}

export function useFixtures(params?: {
  status?: string;
  league?: string;
  season?: string;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}) {
  const qs: Record<string, string> = {};
  if (params?.status) qs.status = params.status;
  if (params?.league) qs.league = params.league;
  if (params?.season) qs.season = params.season;
  if (params?.from) qs.from = params.from;
  if (params?.to) qs.to = params.to;
  if (params?.limit) qs.limit = String(params.limit);
  if (params?.offset) qs.offset = String(params.offset);

  return useQuery({
    queryKey: ["fixtures", params],
    queryFn: () =>
      apiClient.get<FixtureListResponse>("/api/v1/fixtures", qs),
    staleTime: 30_000,
  });
}

export function useFixtureDetail(fixtureId: string | null) {
  return useQuery({
    queryKey: ["fixtures", fixtureId],
    queryFn: () =>
      apiClient.get<FixtureDetailResponse>(
        `/api/v1/fixtures/${encodeURIComponent(fixtureId!)}`,
      ),
    enabled: !!fixtureId,
  });
}

export function useFixturesUpcoming(days?: number) {
  const qs: Record<string, string> = {};
  if (days) qs.days = String(days);

  return useQuery({
    queryKey: ["fixtures", "upcoming", days],
    queryFn: () =>
      apiClient.get<FixtureListResponse>("/api/v1/fixtures/upcoming", qs),
    staleTime: 60_000,
  });
}
