"use client";

import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Brain,
  Calendar,
  Coins,
  Database,
  FileText,
  House,
  Link as LinkIcon,
  Loader2,
  Search,
  Settings,
  Shield,
  TrendingUp,
  Wrench,
  Zap,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";

// ── Route items ────────────────────────────────────────────────────────────────

interface PaletteItem {
  id: string;
  label: string;
  description?: string;
  icon: React.ElementType;
  group: string;
  action: () => void;
}

// ── Command palette store (singleton open/close state) ──────────────────────

let _open = false;
let _listeners: Array<(open: boolean) => void> = [];

function setOpen(val: boolean) {
  _open = val;
  _listeners.forEach((l) => l(val));
}

export function openPalette() {
  setOpen(true);
}

export function closePalette() {
  setOpen(false);
}

function usePaletteOpen() {
  const [open, setLocalOpen] = useState(_open);
  useEffect(() => {
    const listener = (v: boolean) => setLocalOpen(v);
    _listeners.push(listener);
    return () => {
      _listeners = _listeners.filter((l) => l !== listener);
    };
  }, []);
  return [open, setOpen] as const;
}

// ── Main component ─────────────────────────────────────────────────────────────

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen_] = usePaletteOpen();
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Global Ctrl+K / Cmd+K listener
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen(!open);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  // Focus input when opened
  useEffect(() => {
    if (open) {
      setQuery("");
      setActiveIdx(0);
      setTimeout(() => inputRef.current?.focus(), 10);
    }
  }, [open]);

  function navigate(href: string) {
    router.push(href);
    setOpen_(false);
  }

  const baseItems: PaletteItem[] = [
    { id: "nav-home", label: "Dashboard", icon: House, group: "Navigation", action: () => navigate("/") },
    { id: "nav-pipeline", label: "Pipeline", icon: Activity, group: "Navigation", action: () => navigate("/pipeline") },
    { id: "nav-kalshi", label: "Kalshi", icon: BarChart3, group: "Navigation", action: () => navigate("/kalshi") },
    { id: "nav-aliases", label: "Aliases", icon: LinkIcon, group: "Navigation", action: () => navigate("/aliases") },
    { id: "nav-fixtures", label: "Fixtures", icon: Calendar, group: "Navigation", action: () => navigate("/fixtures") },
    { id: "nav-predictions", label: "Predictions", icon: Brain, group: "Navigation", action: () => navigate("/predictions") },
    { id: "nav-bets", label: "Bets", icon: Coins, group: "Navigation", action: () => navigate("/bets") },
    { id: "nav-clv", label: "CLV", icon: TrendingUp, group: "Navigation", action: () => navigate("/clv") },
    { id: "nav-risk", label: "Risk", icon: Shield, group: "Navigation", action: () => navigate("/risk") },
    { id: "nav-warehouse", label: "Warehouse", icon: Database, group: "Navigation", action: () => navigate("/warehouse") },
    { id: "nav-diagnostics", label: "Diagnostics", icon: Wrench, group: "Navigation", action: () => navigate("/diagnostics") },
    { id: "nav-logs", label: "Diagnostics › Logs", icon: FileText, group: "Navigation", action: () => navigate("/diagnostics/logs") },
    { id: "nav-audit", label: "Audit", icon: FileText, group: "Navigation", action: () => navigate("/audit") },
    { id: "nav-live-trading", label: "Live Trading", icon: AlertTriangle, group: "Navigation", action: () => navigate("/live-trading") },
    { id: "nav-settings", label: "Settings", icon: Settings, group: "Navigation", action: () => navigate("/settings") },
    {
      id: "action-pipeline-cycle",
      label: "Run pipeline cycle",
      description: "POST /api/v1/pipeline/cycle",
      icon: Activity,
      group: "Actions",
      action: () => {
        void fetch("/api/v1/pipeline/cycle", { method: "POST", credentials: "include" })
          .then(() => toast.success("Pipeline cycle started"))
          .catch(() => toast.error("Failed to start pipeline cycle"));
        setOpen_(false);
      },
    },
    {
      id: "action-check-conditions",
      label: "Check live trading conditions",
      description: "Run §3 gate checks",
      icon: AlertTriangle,
      group: "Actions",
      action: () => {
        navigate("/live-trading");
      },
    },
    {
      id: "action-backfill-clv",
      label: "Backfill CLV",
      description: "Recalculate closing-line value",
      icon: RefreshCw,
      group: "Actions",
      action: () => {
        void fetch("/api/v1/clv/backfill", { method: "POST", credentials: "include" })
          .then(() => toast.success("CLV backfill started"))
          .catch(() => toast.error("Failed to start CLV backfill"));
        setOpen_(false);
      },
    },
    {
      id: "action-reset-cb",
      label: "Reset circuit breaker",
      description: "POST /diagnostics/circuit-breaker/reset",
      icon: RotateCcw,
      group: "Actions",
      action: () => {
        void fetch("/api/v1/diagnostics/circuit-breaker/reset", {
          method: "POST",
          credentials: "include",
        })
          .then(() => toast.success("Circuit breaker reset"))
          .catch(() => toast.error("Failed to reset circuit breaker"));
        setOpen_(false);
      },
    },
  ];

  const lq = query.toLowerCase();
  const filtered = lq
    ? baseItems.filter(
        (item) =>
          item.label.toLowerCase().includes(lq) ||
          item.description?.toLowerCase().includes(lq) ||
          item.group.toLowerCase().includes(lq),
      )
    : baseItems;

  // Group filtered items
  const groups = filtered.reduce<Record<string, PaletteItem[]>>((acc, item) => {
    (acc[item.group] ??= []).push(item);
    return acc;
  }, {});

  const flatItems = Object.values(groups).flat();

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      setOpen_(false);
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, flatItems.length - 1));
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    }
    if (e.key === "Enter" && flatItems[activeIdx]) {
      flatItems[activeIdx].action();
    }
  }

  // Scroll active item into view
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-idx="${activeIdx}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [activeIdx]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
      onClick={() => setOpen_(false)}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" />

      {/* Panel */}
      <div
        className="relative z-10 w-full max-w-[560px] mx-4 overflow-hidden rounded-xl border border-border bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
      >
        {/* Search input */}
        <div className="flex items-center gap-3 border-b border-border px-4 py-3">
          <Search className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
          <input
            ref={inputRef}
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            placeholder="Search pages, actions…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIdx(0);
            }}
            onKeyDown={(e) => {
              // prevent default form submit on Enter
              if (e.key === "Enter") e.preventDefault();
            }}
          />
          <kbd className="hidden rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground sm:inline">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div ref={listRef} className="max-h-80 overflow-y-auto py-2">
          {flatItems.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-muted-foreground">
              No results for &quot;{query}&quot;
            </p>
          ) : (
            (() => {
              let runningIdx = 0;
              return Object.entries(groups).map(([group, items]) => (
                <div key={group}>
                  <p className="mb-1 mt-2 px-4 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    {group}
                  </p>
                  {items.map((item) => {
                    const idx = runningIdx++;
                    const Icon = item.icon;
                    const isActive = idx === activeIdx;
                    return (
                      <button
                        key={item.id}
                        data-idx={idx}
                        className={`flex w-full items-center gap-3 px-4 py-2 text-left text-sm transition-colors ${
                          isActive
                            ? "bg-accent text-accent-foreground"
                            : "hover:bg-muted"
                        }`}
                        onMouseEnter={() => setActiveIdx(idx)}
                        onClick={item.action}
                      >
                        <Icon className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                        <div className="min-w-0 flex-1">
                          <span className="font-medium">{item.label}</span>
                          {item.description && (
                            <span className="ml-2 text-xs text-muted-foreground">
                              {item.description}
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              ));
            })()
          )}
        </div>

        {/* Footer hint */}
        <div className="flex items-center gap-3 border-t border-border px-4 py-2 text-[10px] text-muted-foreground">
          <span><kbd className="rounded border border-border bg-muted px-1 py-0.5">↑↓</kbd> navigate</span>
          <span><kbd className="rounded border border-border bg-muted px-1 py-0.5">↵</kbd> select</span>
          <span><kbd className="rounded border border-border bg-muted px-1 py-0.5">Esc</kbd> close</span>
        </div>
      </div>
    </div>
  );
}
