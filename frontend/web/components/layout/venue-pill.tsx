"use client";

interface VenueData {
  name: string;
  base_url: string;
  is_demo: boolean;
}

export function VenuePill({ venue }: { venue: VenueData | null }) {
  if (!venue || venue.name === "not configured") {
    return (
      <span className="rounded-full bg-muted px-3 py-1 font-mono text-xs text-muted-foreground">
        NO VENUE
      </span>
    );
  }

  const isDemoVenue = venue.is_demo;
  const pillClass = isDemoVenue
    ? "bg-demo-pill text-white"
    : "bg-production-pill text-white";
  const label = isDemoVenue ? "KALSHI · DEMO" : "KALSHI · PROD";

  return (
    <span
      className={`rounded-full px-3 py-1 font-mono text-xs font-medium ${pillClass}`}
    >
      {label}
    </span>
  );
}
