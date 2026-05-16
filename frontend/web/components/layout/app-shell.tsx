"use client";

import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";
import { CommandPalette } from "@/components/command-palette";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
      <CommandPalette />
    </div>
  );
}
