"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { toast } from "sonner";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useSettings, useSaveSettings, useKalshiCredentials } from "@/lib/api/hooks";
import { useSettingsStore } from "@/lib/stores/settings";
import type { OperatorSettings } from "@/lib/stores/settings";

const THEME_OPTIONS: Array<{ value: OperatorSettings["theme"]; label: string }> = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

const DENSITY_OPTIONS: Array<{ value: OperatorSettings["density"]; label: string }> = [
  { value: "comfortable", label: "Comfortable" },
  { value: "compact", label: "Compact" },
];

const PAGE_SIZE_OPTIONS: Array<OperatorSettings["default_page_size"]> = [25, 50, 100];
const TIME_RANGE_OPTIONS: Array<{ value: OperatorSettings["default_time_range_days"]; label: string }> = [
  { value: 7, label: "7 days" },
  { value: 14, label: "14 days" },
  { value: 30, label: "30 days" },
  { value: 90, label: "90 days" },
];

function Chip<T extends string | number>({
  value,
  current,
  label,
  onClick,
}: {
  value: T;
  current: T;
  label: string;
  onClick: (v: T) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onClick(value)}
      className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
        value === current
          ? "bg-primary text-primary-foreground"
          : "bg-muted text-muted-foreground hover:bg-muted/80"
      }`}
    >
      {label}
    </button>
  );
}

export default function SettingsPage() {
  const router = useRouter();
  const { setTheme } = useTheme();
  const { isLoading: settingsLoading } = useSettings();
  const storeSettings = useSettingsStore((s) => s.settings);
  const { mutate: save, isPending: saving } = useSaveSettings();
  const { data: credentials } = useKalshiCredentials();

  const [local, setLocal] = useState<OperatorSettings>(storeSettings);

  // Sync from store when loaded
  useEffect(() => {
    setLocal(storeSettings);
  }, [storeSettings]);

  function handleSave() {
    save(local, {
      onSuccess: () => {
        // Sync theme immediately to next-themes
        setTheme(local.theme);
        toast.success("Settings saved");
      },
      onError: (err) => toast.error(err.message),
    });
  }

  async function handleSignOut() {
    await fetch("/api/v1/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }

  if (settingsLoading) {
    return (
      <div className="flex flex-col gap-6 p-6">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-36 w-full" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-6 max-w-2xl">
      <h1 className="text-2xl font-bold">Settings</h1>

      {/* Appearance */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Appearance</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <div>
            <p className="mb-2 text-sm font-medium">Theme</p>
            <div className="flex gap-2">
              {THEME_OPTIONS.map((opt) => (
                <Chip
                  key={opt.value}
                  value={opt.value}
                  current={local.theme}
                  label={opt.label}
                  onClick={(v) => setLocal((s) => ({ ...s, theme: v }))}
                />
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 text-sm font-medium">Density</p>
            <div className="flex gap-2">
              {DENSITY_OPTIONS.map((opt) => (
                <Chip
                  key={opt.value}
                  value={opt.value}
                  current={local.density}
                  label={opt.label}
                  onClick={(v) => setLocal((s) => ({ ...s, density: v }))}
                />
              ))}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Compact reduces row height and padding across all tables.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Defaults */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Default Values</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <div>
            <p className="mb-2 text-sm font-medium">Default page size</p>
            <div className="flex gap-2">
              {PAGE_SIZE_OPTIONS.map((v) => (
                <Chip
                  key={v}
                  value={v}
                  current={local.default_page_size}
                  label={String(v)}
                  onClick={(val) => setLocal((s) => ({ ...s, default_page_size: val }))}
                />
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 text-sm font-medium">Default time range</p>
            <div className="flex gap-2">
              {TIME_RANGE_OPTIONS.map((opt) => (
                <Chip
                  key={opt.value}
                  value={opt.value}
                  current={local.default_time_range_days}
                  label={opt.label}
                  onClick={(val) => setLocal((s) => ({ ...s, default_time_range_days: val }))}
                />
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Credentials status */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Credentials Status</CardTitle>
        </CardHeader>
        <CardContent>
          {credentials ? (
            <div className="flex items-center gap-3">
              {credentials.configured ? (
                <CheckCircle2 className="h-5 w-5 text-green-500" />
              ) : (
                <XCircle className="h-5 w-5 text-destructive" />
              )}
              <div>
                <p className="text-sm font-medium">
                  Kalshi API credentials:{" "}
                  <Badge variant={credentials.configured ? "outline" : "destructive"}>
                    {credentials.configured ? "configured" : "missing"}
                  </Badge>
                </p>
                <p className="text-xs text-muted-foreground">
                  Key ID: {credentials.key_id_present ? "present" : "missing"} ·
                  Private key: {credentials.private_key_present ? "present" : "missing"}
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Checking credentials…
            </p>
          )}
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="flex items-center justify-between rounded-lg border border-border p-4">
        <div>
          <p className="text-sm font-medium">Sign out</p>
          <p className="text-xs text-muted-foreground">
            Ends your current operator session.
          </p>
        </div>
        <Button variant="outline" onClick={handleSignOut}>
          Sign out
        </Button>
      </div>

      {/* Save */}
      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving}>
          {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Save settings
        </Button>
      </div>
    </div>
  );
}
