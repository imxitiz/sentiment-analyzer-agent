/**
 * AgentProgress — real-time agent activity feed.
 *
 * Shows a timeline of agent events as they stream in via WebSocket.
 * Each agent phase gets a distinct icon and colour.
 */

import {
  Brain,
  Search,
  Download,
  Sparkles,
  ClipboardCheck,
  CheckCircle2,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import { SESSION_STATUS_LABELS, type AgentEvent, type SessionStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

interface AgentProgressProps {
  events: AgentEvent[];
  status: SessionStatus;
}

const AGENT_META: Record<
  string,
  { icon: typeof Brain; color: string; label: string }
> = {
  planner: { icon: Brain, color: "text-violet-500", label: "Planner" },
  searcher: { icon: Search, color: "text-blue-500", label: "Searcher" },
  scraper: { icon: Download, color: "text-amber-500", label: "Scraper" },
  cleaner: { icon: ClipboardCheck, color: "text-teal-500", label: "Cleaner" },
  analyser: { icon: Sparkles, color: "text-rose-500", label: "Analyser" },
  orchestrator: { icon: Brain, color: "text-primary", label: "Orchestrator" },
};

function getAgentMeta(agent: string) {
  return (
    AGENT_META[agent] ?? {
      icon: Brain,
      color: "text-muted-foreground",
      label: agent || "System",
    }
  );
}

function EventTypeIcon({ type }: { type: string }) {
  switch (type) {
    case "agent_complete":
    case "pipeline_complete":
      return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />;
    case "error":
      return <AlertTriangle className="h-3.5 w-3.5 text-red-500" />;
    default:
      return <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />;
  }
}

export function AgentProgress({ events, status }: AgentProgressProps) {
  // Filter out status_change events — they're noise in the UI
  const visibleEvents = events.filter((e) => e.type !== "status_change");

  if (visibleEvents.length === 0) return null;

  return (
    <div className="space-y-1.5 py-3 max-w-3xl mx-auto">
      {/* Status badge */}
      <div className="flex items-center gap-2 px-3 py-1.5 mb-2">
        <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
        <span className="text-xs font-medium text-blue-500">
          {SESSION_STATUS_LABELS[status]}
        </span>
      </div>

      {/* Event list */}
      <div className="space-y-1">
        {visibleEvents.map((event, idx) => {
          const meta = getAgentMeta(event.agent);
          const AgentIcon = meta.icon;
          const isLast = idx === visibleEvents.length - 1;
          const isComplete =
            event.type === "agent_complete" ||
            event.type === "pipeline_complete";

          return (
            <div
              key={idx}
              className={cn(
                "flex items-start gap-3 px-3 py-2 rounded-lg text-sm transition-all",
                isLast && !isComplete && "bg-muted/50",
                isComplete && "opacity-70",
              )}
            >
              {/* Agent icon */}
              <div className={cn("mt-0.5 shrink-0", meta.color)}>
                <AgentIcon className="h-4 w-4" />
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className={cn("font-medium text-xs", meta.color)}>
                    {meta.label}
                  </span>
                  <EventTypeIcon type={event.type} />
                </div>
                <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                  {event.message}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
