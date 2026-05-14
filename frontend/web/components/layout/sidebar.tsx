"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Brain,
  Calendar,
  ChevronLeft,
  ChevronRight,
  Coins,
  Database,
  FileText,
  House,
  Link as LinkIcon,
  Settings,
  Shield,
  TrendingUp,
  Wrench,
} from "lucide-react";
import { Separator } from "@/components/ui/separator";

interface NavItem {
  label: string;
  href: string;
  icon: React.ElementType;
  destructive?: boolean;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

const NAV_SECTIONS: NavSection[] = [
  {
    title: "OVERVIEW",
    items: [
      { label: "Home", href: "/", icon: House },
      { label: "Pipeline", href: "/pipeline", icon: Activity },
    ],
  },
  {
    title: "MARKETS",
    items: [
      { label: "Kalshi", href: "/kalshi", icon: BarChart3 },
      { label: "Aliases", href: "/aliases", icon: LinkIcon },
      { label: "Fixtures", href: "/fixtures", icon: Calendar },
    ],
  },
  {
    title: "MODELING",
    items: [
      { label: "Predictions", href: "/predictions", icon: Brain },
      { label: "Bets", href: "/bets", icon: Coins },
      { label: "CLV", href: "/clv", icon: TrendingUp },
    ],
  },
  {
    title: "OPERATIONS",
    items: [
      { label: "Risk", href: "/risk", icon: Shield },
      { label: "Warehouse", href: "/warehouse", icon: Database },
      { label: "Diagnostics", href: "/diagnostics", icon: Wrench },
      { label: "Audit", href: "/audit", icon: FileText },
    ],
  },
];

const BOTTOM_ITEMS: NavItem[] = [
  { label: "Settings", href: "/settings", icon: Settings },
  {
    label: "Live Trading",
    href: "/live-trading",
    icon: AlertTriangle,
    destructive: true,
  },
];

const LS_KEY = "sidebar-collapsed";

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem(LS_KEY) === "true";
  });

  function toggle() {
    setCollapsed((prev) => {
      localStorage.setItem(LS_KEY, String(!prev));
      return !prev;
    });
  }

  function isActive(href: string) {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  return (
    <aside
      className={`flex h-screen flex-col border-r border-border bg-card transition-all duration-200 ${
        collapsed ? "w-16" : "w-[260px]"
      }`}
    >
      <div className="flex h-14 items-center px-4">
        {!collapsed && (
          <span className="font-mono text-sm font-bold text-accent">
            footy-ev
          </span>
        )}
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-2 py-2">
        {NAV_SECTIONS.map((section) => (
          <div key={section.title} className="mb-4">
            {!collapsed && (
              <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {section.title}
              </p>
            )}
            {section.items.map((item) => (
              <NavLink
                key={item.href}
                item={item}
                active={isActive(item.href)}
                collapsed={collapsed}
              />
            ))}
          </div>
        ))}
      </nav>

      <div className="px-2 pb-2">
        <Separator className="mb-2" />
        {BOTTOM_ITEMS.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            active={isActive(item.href)}
            collapsed={collapsed}
          />
        ))}
        <button
          onClick={toggle}
          className="mt-2 flex w-full items-center justify-center rounded-md p-2 text-muted-foreground hover:bg-muted"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>
    </aside>
  );
}

function NavLink({
  item,
  active,
  collapsed,
}: {
  item: NavItem;
  active: boolean;
  collapsed: boolean;
}) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      title={collapsed ? item.label : undefined}
      className={`flex items-center gap-3 rounded-md px-2 py-1.5 text-sm transition-colors ${
        active
          ? "border-l-2 border-accent bg-muted font-medium text-foreground"
          : "text-muted-foreground hover:bg-muted hover:text-foreground"
      } ${item.destructive ? "text-destructive hover:text-destructive" : ""}`}
    >
      <Icon size={18} />
      {!collapsed && <span>{item.label}</span>}
    </Link>
  );
}
