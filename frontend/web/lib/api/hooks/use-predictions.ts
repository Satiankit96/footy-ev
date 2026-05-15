import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../client";

export interface PredictionResponse {
  prediction_id: string;
  fixture_id: string;
  market: string;
  selection: string;
  p_raw: number;
  p_calibrated: number;
  sigma_p: number | null;
  model_version: string;
  features_hash: string;
  as_of: string | null;
  generated_at: string | null;
  run_id: string | null;
}

export interface PredictionListResponse {
  predictions: PredictionResponse[];
  total: number;
}

export interface PredictionFeatureItem {
  name: string;
  value: number | null;
  description: string;
}

export interface PredictionFeaturesResponse {
  prediction_id: string;
  fixture_id: string;
  features_hash: string;
  features: PredictionFeatureItem[];
  error: string | null;
}

export interface PredictionRunResponse {
  job_id: string;
  status: string;
}

export function usePredictions(params?: {
  fixture_id?: string;
  model_version?: string;
  market?: string;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}) {
  const qs: Record<string, string> = {};
  if (params?.fixture_id) qs.fixture_id = params.fixture_id;
  if (params?.model_version) qs.model_version = params.model_version;
  if (params?.market) qs.market = params.market;
  if (params?.from) qs.from = params.from;
  if (params?.to) qs.to = params.to;
  if (params?.limit) qs.limit = String(params.limit);
  if (params?.offset) qs.offset = String(params.offset);

  return useQuery({
    queryKey: ["predictions", params],
    queryFn: () =>
      apiClient.get<PredictionListResponse>("/api/v1/predictions", qs),
    staleTime: 30_000,
  });
}

export function usePredictionDetail(predictionId: string | null) {
  return useQuery({
    queryKey: ["predictions", predictionId],
    queryFn: () =>
      apiClient.get<PredictionResponse>(
        `/api/v1/predictions/${encodeURIComponent(predictionId!)}`,
      ),
    enabled: !!predictionId,
  });
}

export function usePredictionFeatures(predictionId: string | null) {
  return useQuery({
    queryKey: ["predictions", predictionId, "features"],
    queryFn: () =>
      apiClient.get<PredictionFeaturesResponse>(
        `/api/v1/predictions/${encodeURIComponent(predictionId!)}/features`,
      ),
    enabled: !!predictionId,
  });
}

export function useRunPredictions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (fixture_ids?: string[]) =>
      apiClient.post<PredictionRunResponse>("/api/v1/predictions/run", {
        fixture_ids: fixture_ids ?? null,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["predictions"] });
    },
  });
}
