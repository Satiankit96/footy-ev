"use client";

import Link from "next/link";
import { ArrowLeft, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useWarehousePlayers } from "@/lib/api/hooks";

export default function PlayersPage() {
  const { data } = useWarehousePlayers();

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/warehouse">
          <Button variant="ghost" size="sm">
            <ArrowLeft size={14} />
            Back
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold">Players</h1>
          <p className="text-sm text-muted-foreground">Squad data browser</p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Players</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-start gap-3 rounded-md border border-border bg-muted/30 p-4 text-sm">
            <Info size={16} className="mt-0.5 shrink-0 text-muted-foreground" />
            <p className="text-muted-foreground">
              {data?.note ?? "No players table in current schema — squad data not yet ingested."}
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
