/**
 * Session page — the main workspace for a single analysis.
 *
 * Two modes:
 *   1. **Chat mode** (default): Shows messages, progress, topic input
 *   2. **Dashboard mode**: Shows sentiment analysis results with charts
 *
 * Automatically switches to dashboard when analysis completes.
 * User can toggle between modes via tabs.
 */

import { useState, useEffect } from "react";
import { useParams } from "@tanstack/react-router";
import { MessageSquare, BarChart3, Loader2, AlertCircle, RefreshCw, Clock, GitCompare } from "lucide-react";
import { useSession, useRefreshAnalysis, useSwitchVersion } from "@/hooks/use-sessions";
import { useSessionWebSocket } from "@/hooks/use-websocket";
import { ChatView } from "@/components/chat/chat-view";
import { DashboardView } from "@/components/dashboard/dashboard-view";
import { ComparisonView } from "@/components/dashboard/comparison-view";
import { ExportButton } from "@/components/dashboard/export-button";
import { VersionSwitcher } from "@/components/ui/version-switcher";
import { cn } from "@/lib/utils";
import type { ViewMode } from "@/lib/types";
import { isSessionActive } from "@/lib/types";

export function SessionPage() {
  const { sessionId } = useParams({ from: "/session/$sessionId" });
  const { data: session, isLoading, error } = useSession(sessionId);
  const { events, isConnected } = useSessionWebSocket(sessionId);
  const refreshAnalysis = useRefreshAnalysis();
  const switchVersion = useSwitchVersion();
  const [viewMode, setViewMode] = useState<ViewMode>("chat");

  // Auto-switch to dashboard when analysis completes
  useEffect(() => {
    if (session?.status === "completed" && session.result) {
      setViewMode("dashboard");
    }
  }, [session?.status, session?.result]);

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !session) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center space-y-2">
          <AlertCircle className="h-8 w-8 mx-auto text-destructive" />
          <p className="text-sm text-muted-foreground">
            {error?.message || "Session not found"}
          </p>
        </div>
      </div>
    );
  }

  const showTabs = session.status === "completed" && session.result;
  const isRunning = isSessionActive(session.status);
  const canRefresh = session.status === "completed" && session.topic;
  const hasMultipleVersions = session.version_history.length > 0;

  const handleRefresh = () => {
    if (!canRefresh) return;
    refreshAnalysis.mutate(session.id, {
      onSuccess: () => setViewMode("chat"),
    });
  };

  const handleSwitchVersion = (version: number) => {
    switchVersion.mutate(
      { sessionId: session.id, version },
      { onSuccess: (s) => s.result && setViewMode("dashboard") },
    );
  };

  // Determine the highest version (for the "Latest" tag)
  const maxVersion = Math.max(
    session.version,
    ...session.version_history.map((v) => v.version),
  );
  const isViewingLatest = session.version === maxVersion;

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Header with tabs */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2 shrink-0">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold truncate max-w-md">
            {session.topic || "New Analysis"}
          </h2>
          {session.version > 1 && (
            <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-accent text-accent-foreground">
              v{session.version}
            </span>
          )}
          {!isViewingLatest && session.version_history.length > 0 && (
            <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-500/10 text-amber-500">
              Viewing older version
            </span>
          )}
          {isConnected && isRunning && (
            <span className="flex items-center gap-1 text-xs text-emerald-500">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Live
            </span>
          )}
          {/* Updated-at timestamp */}
          {session.updated_at && (
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
              <Clock className="h-3 w-3" />
              {formatUpdatedAt(session.updated_at)}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Version switcher dropdown */}
          <VersionSwitcher
            session={session}
            onSwitch={handleSwitchVersion}
            isPending={switchVersion.isPending}
          />

          {/* Export button */}
          {showTabs && (
            <ExportButton sessionId={session.id} version={session.version} />
          )}

          {canRefresh && (
            <button
              onClick={handleRefresh}
              disabled={refreshAnalysis.isPending}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium",
                "border border-border text-muted-foreground",
                "hover:bg-accent hover:text-accent-foreground transition-colors",
                "disabled:opacity-50 disabled:cursor-not-allowed",
              )}
              title="Re-run analysis to get fresh data"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", refreshAnalysis.isPending && "animate-spin")} />
              {refreshAnalysis.isPending ? "Refreshing…" : "Refresh"}
            </button>
          )}

          {showTabs && (
          <div className="flex items-center rounded-lg border border-border p-0.5">
            <button
              onClick={() => setViewMode("chat")}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
                viewMode === "chat"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <MessageSquare className="h-3.5 w-3.5" />
              Chat
            </button>
            <button
              onClick={() => setViewMode("dashboard")}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
                viewMode === "dashboard"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <BarChart3 className="h-3.5 w-3.5" />
              Dashboard
            </button>
            {hasMultipleVersions && (
              <button
                onClick={() => setViewMode("compare")}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
                  viewMode === "compare"
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <GitCompare className="h-3.5 w-3.5" />
                Compare
              </button>
            )}
          </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {viewMode === "chat" ? (
          <ChatView session={session} events={events} />
        ) : viewMode === "compare" ? (
          <div className="h-full overflow-y-auto p-6">
            <ComparisonView session={session} />
          </div>
        ) : session.result ? (
          <DashboardView result={session.result} />
        ) : (
          <ChatView session={session} events={events} />
        )}
      </div>
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────

function formatUpdatedAt(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();

  if (diff < 60_000) return "Updated just now";
  if (diff < 3_600_000) return `Updated ${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `Updated ${Math.floor(diff / 3_600_000)}h ago`;
  return `Updated ${d.toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}`;
}
