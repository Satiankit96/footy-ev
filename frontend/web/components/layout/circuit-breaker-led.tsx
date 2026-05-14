"use client";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface BreakerState {
  state: string;
  reason: string | null;
}

export function CircuitBreakerLED({ breaker }: { breaker: BreakerState | null }) {
  const isOk = !breaker || breaker.state === "ok";
  const tooltipText = isOk
    ? "Circuit breaker OK"
    : `TRIPPED: ${breaker?.reason ?? "unknown"}`;

  return (
    <Tooltip>
      <TooltipTrigger
        className={`inline-block h-3 w-3 rounded-full ${
          isOk
            ? "bg-success"
            : "animate-pulse bg-destructive"
        }`}
        aria-label={tooltipText}
      />
      <TooltipContent>
        <p className="text-xs">{tooltipText}</p>
      </TooltipContent>
    </Tooltip>
  );
}
