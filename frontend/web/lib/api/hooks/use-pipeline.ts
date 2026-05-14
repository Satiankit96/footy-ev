import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../client";
import type { components } from "../v1.gen";

export type PipelineStatusResponse =
  components["schemas"]["PipelineStatusResponse"];
export type LoopStateResponse = components["schemas"]["LoopStateResponse"];
export type StartCycleResponse = components["schemas"]["StartCycleResponse"];
export type StartLoopResponse = components["schemas"]["StartLoopResponse"];
export type JobResponse = components["schemas"]["JobResponse"];
export type JobListResponse = components["schemas"]["JobListResponse"];
export type FreshnessEntry = components["schemas"]["FreshnessEntry"];

export function usePipelineStatus() {
  return useQuery({
    queryKey: ["pipeline", "status"],
    queryFn: () =>
      apiClient.get<PipelineStatusResponse>("/api/v1/pipeline/status"),
    refetchInterval: 10_000,
  });
}

export function usePipelineLoop() {
  return useQuery({
    queryKey: ["pipeline", "loop"],
    queryFn: () => apiClient.get<LoopStateResponse>("/api/v1/pipeline/loop"),
  });
}

export function usePipelineJobs(params?: { status?: string; limit?: number }) {
  const qs: Record<string, string> = {};
  if (params?.status) qs.status = params.status;
  if (params?.limit) qs.limit = String(params.limit);

  return useQuery({
    queryKey: ["pipeline", "jobs", params],
    queryFn: () => apiClient.get<JobListResponse>("/api/v1/pipeline/jobs", qs),
    refetchInterval: 5_000,
  });
}

export function useStartCycle() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiClient.post<StartCycleResponse>("/api/v1/pipeline/cycle"),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["pipeline"] });
    },
  });
}

export function useStartLoop() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (intervalMin: number) =>
      apiClient.post<StartLoopResponse>("/api/v1/pipeline/loop/start", {
        interval_min: intervalMin,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["pipeline"] });
    },
  });
}

export function useStopLoop() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.post("/api/v1/pipeline/loop/stop"),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["pipeline"] });
    },
  });
}
