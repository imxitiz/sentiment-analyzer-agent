/**
 * Sidebar — session list and navigation.
 *
 * Features:
 *   • "New Analysis" button
 *   • Session list with status indicators
 *   • Active session highlighting
 *   • Session deletion
 *   • Collapsible on mobile
 */

import { useState } from "react";
import { useNavigate, useParams } from "@tanstack/react-router";
import {
  Plus,
  MessageSquare,
  BarChart3,
  Loader2,
  AlertCircle,
  Trash2,
  ChevronLeft,
  ChevronRight,
  Activity,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { useSessionList, useCreateSession, useDeleteSession } from "@/hooks/use-sessions";
import {
  SESSION_STATUS_LABELS,
  isSessionActive,
  type Session,
  type SessionStatus,
} from "@/lib/types";
import { cn } from "@/lib/utils";

function statusIcon(status: SessionStatus) {
  switch (status) {
    case "completed":
      return <BarChart3 className="h-4 w-4 text-emerald-500" />;
    case "error":
      return <AlertCircle className="h-4 w-4 text-red-500" />;
    case "idle":
      return <MessageSquare className="h-4 w-4 text-muted-foreground" />;
    default:
      return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
  }
}

function SessionItem({
  session,
  isActive,
  onClick,
  onDelete,
}: {
  session: Session;
  isActive: boolean;
  onClick: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      className={cn(
        "group flex items-center gap-3 rounded-lg px-3 py-2.5 cursor-pointer transition-colors",
        "hover:bg-accent",
        isActive && "bg-accent",
      )}
      onClick={onClick}
    >
      {statusIcon(session.status)}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">
          {session.topic || "New Analysis"}
          {session.version > 1 && (
            <span className="ml-1.5 text-[10px] font-semibold text-muted-foreground">
              v{session.version}
            </span>
          )}
        </p>
        <div className="flex items-center gap-2">
          <p className="text-xs text-muted-foreground truncate">
            {SESSION_STATUS_LABELS[session.status]}
          </p>
          {session.version_history.length > 0 && (
            <span className="text-[10px] text-muted-foreground/60">
              · {session.version_history.length + 1} versions
            </span>
          )}
        </div>
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-destructive/10 hover:text-destructive transition-all"
        title="Delete session"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const params = useParams({ strict: false }) as { sessionId?: string };
  const activeId = params.sessionId;

  const { data: sessions = [], isLoading } = useSessionList();
  const createSession = useCreateSession();
  const deleteSession = useDeleteSession();

  const handleNewSession = async () => {
    try {
      const session = await createSession.mutateAsync({});
      navigate({ to: "/session/$sessionId", params: { sessionId: session.id } });
    } catch {
      // Handle error silently — query will show stale data
    }
  };

  const handleSessionClick = (session: Session) => {
    navigate({ to: "/session/$sessionId", params: { sessionId: session.id } });
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteSession.mutateAsync(id);
      if (activeId === id) {
        navigate({ to: "/" });
      }
    } catch {
      // Handle error silently
    }
  };

  if (collapsed) {
    return (
      <div className="flex flex-col items-center w-14 border-r border-border bg-sidebar py-4 gap-3">
        <button
          onClick={() => setCollapsed(false)}
          className="p-2 rounded-lg hover:bg-accent transition-colors"
          title="Expand sidebar"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
        <ThemeToggle collapsed />
        <button
          onClick={handleNewSession}
          className="p-2 rounded-lg hover:bg-accent transition-colors"
          title="New analysis"
        >
          <Plus className="h-4 w-4" />
        </button>
        <div className="flex-1 w-full px-1.5 space-y-1.5 overflow-y-auto">
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => handleSessionClick(s)}
              className={cn(
                "w-full p-2 rounded-lg flex justify-center transition-colors",
                "hover:bg-accent",
                activeId === s.id && "bg-accent",
              )}
              title={s.topic || "New Analysis"}
            >
              {statusIcon(s.status)}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col w-72 border-r border-border bg-sidebar">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-4 border-b border-border">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-primary" />
          <h1 className="font-semibold text-sm">Sentiment Analyzer</h1>
        </div>
        <button
          onClick={() => setCollapsed(true)}
          className="p-1.5 rounded-lg hover:bg-accent transition-colors"
          title="Collapse sidebar"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
      </div>

      {/* New Analysis Button */}
      <div className="px-3 py-3">
        <Button
          onClick={handleNewSession}
          className="w-full justify-start gap-2"
          variant="outline"
          disabled={createSession.isPending}
        >
          {createSession.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          New Analysis
        </Button>
      </div>

      {/* Session List */}
      <div className="flex-1 overflow-y-auto px-2 pb-4">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="text-center py-8 px-4">
            <MessageSquare className="h-8 w-8 mx-auto mb-3 text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground">No sessions yet</p>
            <p className="text-xs text-muted-foreground/70 mt-1">
              Start a new analysis to begin
            </p>
          </div>
        ) : (
          <div className="space-y-1">
            {sessions.map((session) => (
              <SessionItem
                key={session.id}
                session={session}
                isActive={activeId === session.id}
                onClick={() => handleSessionClick(session)}
                onDelete={() => handleDelete(session.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Theme + Footer */}
      <div className="px-3 py-3 border-t border-border space-y-2">
        <ThemeToggle />
        <p className="text-xs text-muted-foreground text-center">
          Sentiment Analyzer Agent v0.1
        </p>
      </div>
    </div>
  );
}
