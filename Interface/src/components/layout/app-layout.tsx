/**
 * App Layout — main shell with sidebar and content area.
 *
 * Provides:
 *   • Collapsible sidebar with session list
 *   • Header with app branding
 *   • Main content area (children/Outlet)
 */

import type { ReactNode } from "react";
import { Sidebar } from "./sidebar";

interface AppLayoutProps {
  children: ReactNode;
}

export function AppLayout({ children }: AppLayoutProps) {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      {/* Sidebar */}
      <Sidebar />

      {/* Main content */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {children}
      </main>
    </div>
  );
}
