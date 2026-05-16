import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { apiClient } from "../client";
import { useSettingsStore } from "@/lib/stores/settings";
import type { OperatorSettings } from "@/lib/stores/settings";

export type { OperatorSettings };

export interface SettingsResponse {
  settings: OperatorSettings;
}

export function useSettings() {
  const setSettings = useSettingsStore((s) => s.setSettings);

  const query = useQuery<SettingsResponse>({
    queryKey: ["settings"],
    queryFn: () => apiClient.get<SettingsResponse>("/api/v1/settings"),
    staleTime: 60_000,
  });

  useEffect(() => {
    if (query.data) {
      setSettings(query.data.settings);
    }
  }, [query.data, setSettings]);

  return query;
}

export function useSaveSettings() {
  const qc = useQueryClient();
  const setSettings = useSettingsStore((s) => s.setSettings);

  return useMutation<SettingsResponse, Error, OperatorSettings>({
    mutationFn: (body) =>
      apiClient.put<SettingsResponse>("/api/v1/settings", body),
    onSuccess: (data) => {
      setSettings(data.settings);
      void qc.invalidateQueries({ queryKey: ["settings"] });
    },
  });
}
