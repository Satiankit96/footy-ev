import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../client";
import type { components } from "../v1.gen";

export type HealthResponse = components["schemas"]["HealthResponse"];

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => apiClient.get<HealthResponse>("/api/v1/health"),
    refetchInterval: 30_000,
  });
}
