import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../client";
import type { components } from "../v1.gen";

export type MeResponse = components["schemas"]["MeResponse"];

export function useMe() {
  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => apiClient.get<MeResponse>("/api/v1/auth/me"),
    retry: false,
  });
}
