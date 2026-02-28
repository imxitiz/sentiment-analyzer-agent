/**
 * Version switcher — dropdown to browse historical analysis versions.
 *
 * Shows the current active version with a dropdown listing all versions.
 * Each version displays its number, completion time, and post count.
 * Clicking a version swaps the session's active data to that version.
 */

import { useState, useRef, useEffect } from "react";
import { History, ChevronDown, Check, Clock, BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Session, VersionSnapshot } from "@/lib/types";

/** Format a datetime string to a short human-readable form. */
function formatTime(iso: string | null): string {
  if (!iso) return "In progress";
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();

  // Less than 1 minute
  if (diff < 60_000) return "Just now";
  // Less than 1 hour
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  // Less than 24 hours
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  // Same year
  if (d.getFullYear() === now.getFullYear()) {
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

interface VersionSwitcherProps {
  session: Session;
  onSwitch: (version: number) => void;
  isPending?: boolean;
}

export function VersionSwitcher({ session, onSwitch, isPending }: VersionSwitcherProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  // Build sorted list of all versions (history + current)
  const allVersions = buildVersionList(session);

  // Only show if there are multiple versions
  if (allVersions.length <= 1) {
    return null;
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        disabled={isPending}
        className={cn(
          "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium",
          "border border-border text-muted-foreground",
          "hover:bg-accent hover:text-accent-foreground transition-colors",
          "disabled:opacity-50 disabled:cursor-not-allowed",
        )}
      >
        <History className="h-3.5 w-3.5" />
        <span>v{session.version}</span>
        <ChevronDown className={cn("h-3 w-3 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 z-50 min-w-[260px] rounded-lg border border-border bg-popover p-1 shadow-lg">
          <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground border-b border-border mb-1">
            Version History
          </div>
          {allVersions.map((v) => (
            <button
              key={v.version}
              onClick={() => {
                if (v.version !== session.version) {
                  onSwitch(v.version);
                }
                setOpen(false);
              }}
              className={cn(
                "w-full flex items-center gap-3 px-2 py-2 rounded-md text-left transition-colors",
                v.version === session.version
                  ? "bg-accent text-accent-foreground"
                  : "hover:bg-accent/50 text-foreground",
              )}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold">
                    v{v.version}
                  </span>
                  {v.version === session.version && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-medium">
                      Active
                    </span>
                  )}
                  {v.isLatest && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-500 font-medium">
                      Latest
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3 mt-0.5 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {formatTime(v.completed_at)}
                  </span>
                  {v.postCount > 0 && (
                    <span className="flex items-center gap-1">
                      <BarChart3 className="h-3 w-3" />
                      {v.postCount} posts
                    </span>
                  )}
                </div>
              </div>
              {v.version === session.version && (
                <Check className="h-4 w-4 text-primary shrink-0" />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────

interface VersionEntry {
  version: number;
  completed_at: string | null;
  postCount: number;
  isLatest: boolean;
}

function buildVersionList(session: Session): VersionEntry[] {
  const maxVersion = Math.max(
    session.version,
    ...session.version_history.map((v) => v.version),
  );

  const entries: VersionEntry[] = [];

  // Add archived versions
  for (const snap of session.version_history) {
    entries.push({
      version: snap.version,
      completed_at: snap.completed_at,
      postCount: snap.result?.summary?.total_posts ?? 0,
      isLatest: snap.version === maxVersion,
    });
  }

  // Add current active version
  entries.push({
    version: session.version,
    completed_at: session.result?.completed_at ?? session.updated_at,
    postCount: session.result?.summary?.total_posts ?? 0,
    isLatest: session.version === maxVersion,
  });

  // Sort descending (newest first)
  entries.sort((a, b) => b.version - a.version);

  return entries;
}
