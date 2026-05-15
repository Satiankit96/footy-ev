import { useQuery, useMutation } from "@tanstack/react-query";
import { apiClient } from "../client";

export interface BootstrapRunRequest {
  mode?: string;
  create_fixtures?: boolean;
  fixture_path?: string | null;
}

export interface BootstrapRunResponse {
  job_id: string;
  status: string;
}

export interface BootstrapPreviewResponse {
  total_events: number;
  already_mapped: number;
  would_resolve: number;
  would_create_fixture: number;
  would_skip: number;
}

export interface BootstrapJobResponse {
  job_id: string;
  job_type: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  progress: Record<string, unknown>[];
}

export interface BootstrapJobListResponse {
  jobs: BootstrapJobResponse[];
}

export function useBootstrapPreview(params?: {
  mode?: string;
  fixture_path?: string;
}) {
  const qs: Record<string, string> = {};
  if (params?.mode) qs.mode = params.mode;
  if (params?.fixture_path) qs.fixture_path = params.fixture_path;

  return useQuery({
    queryKey: ["bootstrap", "preview", params],
    queryFn: () =>
      apiClient.get<BootstrapPreviewResponse>(
        "/api/v1/bootstrap/preview",
        qs,
      ),
    enabled: false,
  });
}

export function useBootstrapRun() {
  return useMutation({
    mutationFn: (body?: BootstrapRunRequest) =>
      apiClient.post<BootstrapRunResponse>("/api/v1/bootstrap/run", body),
  });
}

export function useBootstrapJobs(limit?: number) {
  const qs: Record<string, string> = {};
  if (limit) qs.limit = String(limit);

  return useQuery({
    queryKey: ["bootstrap", "jobs"],
    queryFn: () =>
      apiClient.get<BootstrapJobListResponse>("/api/v1/bootstrap/jobs", qs),
    staleTime: 10_000,
  });
}

export function useBootstrapJob(jobId: string | null) {
  return useQuery({
    queryKey: ["bootstrap", "jobs", jobId],
    queryFn: () =>
      apiClient.get<BootstrapJobResponse>(`/api/v1/bootstrap/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: 2000,
  });
}
