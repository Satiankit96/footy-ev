import { format, parseISO, formatDistanceToNow } from "date-fns";

export function formatTimestamp(iso: string): string {
  try {
    return format(parseISO(iso), "MMM d, yyyy HH:mm");
  } catch {
    return iso;
  }
}

export function formatAge(iso: string | null): string {
  if (!iso) return "—";
  try {
    return formatDistanceToNow(parseISO(iso), { addSuffix: true });
  } catch {
    return iso;
  }
}

export function formatClv(pct: number | null): string {
  if (pct === null) return "—";
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

export function clvColor(pct: number | null): string {
  if (pct === null) return "text-muted-foreground";
  if (pct >= 2) return "text-green-500";
  if (pct >= 0) return "text-green-400";
  if (pct >= -2) return "text-yellow-500";
  return "text-destructive";
}
