"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface HealthResponse {
  status: string;
  version: string;
  uptime_s: number;
}

export default function Home() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/v1/health")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: HealthResponse) => setHealth(data))
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <Card className="w-full max-w-md">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-2xl font-bold tracking-tight">
            footy-ev
          </CardTitle>
          {health ? (
            <Badge className="bg-success text-success-foreground">
              API Connected
            </Badge>
          ) : error ? (
            <Badge variant="destructive">API Unreachable</Badge>
          ) : (
            <Badge variant="secondary">Connecting...</Badge>
          )}
        </CardHeader>
        <CardContent>
          {health ? (
            <dl className="space-y-2 font-mono text-sm">
              <div className="flex justify-between">
                <dt className="text-muted-foreground">status</dt>
                <dd>{health.status}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">version</dt>
                <dd>{health.version}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">uptime</dt>
                <dd>{health.uptime_s}s</dd>
              </div>
            </dl>
          ) : error ? (
            <p className="text-sm text-destructive">
              Could not reach the API backend. Is uvicorn running on :8000?
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              Checking API health...
            </p>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
