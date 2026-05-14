"use client";

import { usePathname, useRouter } from "next/navigation";
import { Moon, Sun, User } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { VenuePill } from "./venue-pill";
import { CircuitBreakerLED } from "./circuit-breaker-led";

interface ShellData {
  venue: { name: string; base_url: string; is_demo: boolean } | null;
  circuit_breaker: { state: string; reason: string | null } | null;
}

const ROUTE_TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/pipeline": "Pipeline",
  "/kalshi": "Kalshi",
  "/aliases": "Aliases",
  "/fixtures": "Fixtures",
  "/predictions": "Predictions",
  "/bets": "Bets",
  "/clv": "CLV",
  "/risk": "Risk",
  "/warehouse": "Warehouse",
  "/diagnostics": "Diagnostics",
  "/audit": "Audit",
  "/live-trading": "Live Trading",
  "/settings": "Settings",
};

export function Topbar({ shell }: { shell: ShellData | null }) {
  const pathname = usePathname();
  const router = useRouter();
  const { theme, setTheme } = useTheme();

  const title = ROUTE_TITLES[pathname] ?? pathname.slice(1);

  async function handleSignOut() {
    await fetch("/api/v1/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-card px-6">
      <h1 className="text-lg font-semibold">{title}</h1>

      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label="Toggle theme"
          className="h-8 w-8"
        >
          <Sun className="h-4 w-4 rotate-0 scale-100 transition-transform dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-transform dark:rotate-0 dark:scale-100" />
        </Button>

        <VenuePill venue={shell?.venue ?? null} />
        <CircuitBreakerLED breaker={shell?.circuit_breaker ?? null} />

        <DropdownMenu>
          <DropdownMenuTrigger className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground">
            <User className="h-4 w-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={handleSignOut}>
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
