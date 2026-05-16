"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  FileText,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useCircuitBreaker,
  useResetCircuitBreaker,
  useDiagnosticsMigrations,
  useDiagnosticsEnv,
} from "@/lib/api/hooks";

function formatTs(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function DiagnosticsPage() {
  const { data: cb, isLoading: cbLoading, refetch: refetchCb } = useCircuitBreaker();
  const { mutate: resetCb, isPending: resetting } = useResetCircuitBreaker();
  const { data: migrations, isLoading: migrationsLoading } = useDiagnosticsMigrations();
  const { data: env, isLoading: envLoading } = useDiagnosticsEnv();
  const [resetError, setResetError] = useState<string | null>(null);

  function handleReset() {
    setResetError(null);
    resetCb(undefined, {
      onError: (err) =>
        setResetError(err instanceof Error ? err.message : String(err)),
    });
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Diagnostics</h1>
        <Link href="/diagnostics/logs">
          <Button variant="outline" size="sm">
            <FileText className="mr-2 h-4 w-4" />
            View Logs
          </Button>
        </Link>
      </div>

      {/* Circuit Breaker */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="h-4 w-4" />
            Circuit Breaker
          </CardTitle>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void refetchCb()}
              disabled={cbLoading}
            >
              <RefreshCw className={`h-4 w-4 ${cbLoading ? "animate-spin" : ""}`} />
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={handleReset}
              disabled={resetting || cbLoading}
            >
              {resetting ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              Reset
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {cbLoading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : cb ? (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-3">
                {cb.state === "ok" ? (
                  <CheckCircle2 className="h-5 w-5 text-green-500" />
                ) : (
                  <AlertTriangle className="h-5 w-5 text-destructive" />
                )}
                <Badge variant={cb.state === "ok" ? "outline" : "destructive"}>
                  {cb.state.toUpperCase()}
                </Badge>
              </div>
              {cb.reason && (
                <p className="text-sm text-muted-foreground">
                  Reason: <span className="font-medium text-foreground">{cb.reason}</span>
                </p>
              )}
              {cb.last_tripped_at && (
                <p className="text-sm text-muted-foreground">
                  Last tripped: {formatTs(cb.last_tripped_at)}
                </p>
              )}
              {resetError && (
                <p className="text-sm text-destructive">{resetError}</p>
              )}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* Migrations */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Migrations</CardTitle>
        </CardHeader>
        <CardContent>
          {migrationsLoading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : migrations ? (
            <div className="max-h-64 overflow-y-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-1 font-medium">Migration</th>
                    <th className="pb-1 font-medium">Applied</th>
                    <th className="pb-1 font-medium">Applied At</th>
                  </tr>
                </thead>
                <tbody>
                  {migrations.migrations.map((m) => (
                    <tr key={m.name} className="border-b last:border-0">
                      <td className="py-1.5 font-mono text-xs">{m.name}</td>
                      <td className="py-1.5">
                        {m.applied ? (
                          <CheckCircle2 className="h-4 w-4 text-green-500" />
                        ) : (
                          <AlertTriangle className="h-4 w-4 text-amber-500" />
                        )}
                      </td>
                      <td className="py-1.5 text-muted-foreground">
                        {formatTs(m.applied_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* Environment */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Environment Variables</CardTitle>
        </CardHeader>
        <CardContent>
          {envLoading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : env ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="pb-1 font-medium">Variable</th>
                  <th className="pb-1 font-medium">Required</th>
                  <th className="pb-1 font-medium">Set</th>
                </tr>
              </thead>
              <tbody>
                {env.vars.map((v) => (
                  <tr key={v.name} className="border-b last:border-0">
                    <td className="py-1.5 font-mono text-xs">{v.name}</td>
                    <td className="py-1.5">
                      {v.required ? (
                        <Badge variant="outline" className="text-xs">required</Badge>
                      ) : (
                        <span className="text-muted-foreground text-xs">optional</span>
                      )}
                    </td>
                    <td className="py-1.5">
                      {v.is_set ? (
                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                      ) : (
                        <AlertTriangle
                          className={`h-4 w-4 ${v.required ? "text-destructive" : "text-amber-500"}`}
                        />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
