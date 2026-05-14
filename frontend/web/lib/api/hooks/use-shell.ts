import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../client";
import type { components } from "../v1.gen";

export type ShellResponse = components["schemas"]["ShellResponse"];
export type VenueInfo = components["schemas"]["VenueInfo"];
export type CircuitBreakerInfo = components["schemas"]["CircuitBreakerInfo"];
export type PipelineInfo = components["schemas"]["PipelineInfo"];

export function useShell() {
  return useQuery({
    queryKey: ["shell"],
    queryFn: () => apiClient.get<ShellResponse>("/api/v1/shell"),
    staleTime: 10_000,
  });
}
