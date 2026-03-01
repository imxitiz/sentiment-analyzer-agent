/**
 * ComparisonView — side-by-side comparison of two analysis versions.
 *
 * Shows:
 *   • Narrative summary of changes
 *   • Sentiment delta cards (before/after)
 *   • Platform comparison bars
 *   • Keyword changes (added/removed/common)
 */

import { useState } from "react";
import {
  ArrowUpCircle,
  ArrowDownCircle,
  MinusCircle,
  TrendingUp,
  TrendingDown,
  ArrowRight,
  GitCompare,
  Loader2,
  Plus,
  Minus,
  X,
} from "lucide-react";
import { useCompareAnalysis } from "@/hooks/use-sessions";
import type { ComparisonResult, Session, VersionSnapshot } from "@/lib/types";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────

interface ComparisonViewProps {
  session: Session;
}

interface VersionOption {
  label: string;
  version: number;
  hasPosts: boolean;
}

// ── Helpers ───────────────────────────────────────────────────────────

function buildVersionOptions(session: Session): VersionOption[] {
  const options: VersionOption[] = [];

  // Current active version
  options.push({
    label: `v${session.version} (current)`,
    version: session.version,
    hasPosts: !!session.result,
  });

  // Historical versions
  for (const snap of session.version_history) {
    options.push({
      label: `v${snap.version}`,
      version: snap.version,
      hasPosts: !!snap.result,
    });
  }

  return options.sort((a, b) => a.version - b.version);
}

function DeltaIndicator({ value, suffix = "" }: { value: number; suffix?: string }) {
  if (value > 0.01) {
    return (
      <span className="flex items-center gap-0.5 text-emerald-500 text-xs font-semibold">
        <TrendingUp className="h-3 w-3" />
        +{value.toFixed(2)}{suffix}
      </span>
    );
  }
  if (value < -0.01) {
    return (
      <span className="flex items-center gap-0.5 text-red-500 text-xs font-semibold">
        <TrendingDown className="h-3 w-3" />
        {value.toFixed(2)}{suffix}
      </span>
    );
  }
  return (
    <span className="text-xs text-muted-foreground font-medium">
      No change
    </span>
  );
}

function DirectionBadge({ direction }: { direction: string }) {
  if (direction === "improved") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-500">
        <ArrowUpCircle className="h-3 w-3" />
        Improved
      </span>
    );
  }
  if (direction === "declined") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-red-500/10 text-red-500">
        <ArrowDownCircle className="h-3 w-3" />
        Declined
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-500/10 text-slate-400">
      <MinusCircle className="h-3 w-3" />
      Stable
    </span>
  );
}

// ── Sub-Components ────────────────────────────────────────────────────

function SentimentDeltaCards({ comparison }: { comparison: ComparisonResult }) {
  const s = comparison.sentiment;
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {/* Overall compound */}
      <div className="rounded-lg border border-border bg-card p-4">
        <p className="text-xs text-muted-foreground mb-1">Compound Score</p>
        <div className="flex items-baseline gap-2">
          <span className="text-lg font-bold">{s.avg_compound_before.toFixed(2)}</span>
          <ArrowRight className="h-3 w-3 text-muted-foreground shrink-0" />
          <span className="text-lg font-bold">{s.avg_compound_after.toFixed(2)}</span>
        </div>
        <DeltaIndicator value={s.delta} />
      </div>

      {/* Positive % */}
      <div className="rounded-lg border border-border bg-card p-4">
        <p className="text-xs text-muted-foreground mb-1">Positive %</p>
        <div className="flex items-baseline gap-2">
          <span className="text-lg font-bold text-emerald-500">{s.positive_pct_before.toFixed(1)}</span>
          <ArrowRight className="h-3 w-3 text-muted-foreground shrink-0" />
          <span className="text-lg font-bold text-emerald-500">{s.positive_pct_after.toFixed(1)}</span>
        </div>
        <DeltaIndicator value={s.positive_pct_after - s.positive_pct_before} suffix="%" />
      </div>

      {/* Negative % */}
      <div className="rounded-lg border border-border bg-card p-4">
        <p className="text-xs text-muted-foreground mb-1">Negative %</p>
        <div className="flex items-baseline gap-2">
          <span className="text-lg font-bold text-red-500">{s.negative_pct_before.toFixed(1)}</span>
          <ArrowRight className="h-3 w-3 text-muted-foreground shrink-0" />
          <span className="text-lg font-bold text-red-500">{s.negative_pct_after.toFixed(1)}</span>
        </div>
        <DeltaIndicator value={-(s.negative_pct_after - s.negative_pct_before)} suffix="%" />
      </div>

      {/* Post volume */}
      <div className="rounded-lg border border-border bg-card p-4">
        <p className="text-xs text-muted-foreground mb-1">Total Posts</p>
        <div className="flex items-baseline gap-2">
          <span className="text-lg font-bold">{s.total_posts_before}</span>
          <ArrowRight className="h-3 w-3 text-muted-foreground shrink-0" />
          <span className="text-lg font-bold">{s.total_posts_after}</span>
        </div>
        <DeltaIndicator value={s.total_posts_after - s.total_posts_before} />
      </div>
    </div>
  );
}

function PlatformComparison({ comparison }: { comparison: ComparisonResult }) {
  const plats = comparison.platforms;
  if (plats.length === 0) return null;

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h4 className="text-sm font-semibold mb-3">Platform Shifts</h4>
      <div className="space-y-2">
        {plats.map((p) => (
          <div key={p.platform} className="flex items-center justify-between text-sm">
            <span className="font-medium capitalize w-20">{p.platform}</span>
            <div className="flex items-center gap-2 flex-1 justify-center">
              <span className="text-muted-foreground w-12 text-right">
                {p.before_avg != null ? p.before_avg.toFixed(2) : "—"}
              </span>
              <ArrowRight className="h-3 w-3 text-muted-foreground shrink-0" />
              <span className="text-muted-foreground w-12">
                {p.after_avg != null ? p.after_avg.toFixed(2) : "—"}
              </span>
            </div>
            <div className="w-20 text-right">
              {p.delta != null ? <DeltaIndicator value={p.delta} /> : <span className="text-xs text-muted-foreground">new</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function KeywordChanges({ comparison }: { comparison: ComparisonResult }) {
  const kw = comparison.keywords;
  if (!kw.added.length && !kw.removed.length && !kw.common.length) return null;

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h4 className="text-sm font-semibold mb-3">Keyword Changes</h4>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {kw.added.length > 0 && (
          <div>
            <p className="flex items-center gap-1 text-xs font-semibold text-emerald-500 mb-2">
              <Plus className="h-3 w-3" /> New Keywords
            </p>
            <div className="flex flex-wrap gap-1">
              {kw.added.map((k) => (
                <span key={k} className="px-2 py-0.5 rounded-full text-xs bg-emerald-500/10 text-emerald-500">
                  {k}
                </span>
              ))}
            </div>
          </div>
        )}
        {kw.removed.length > 0 && (
          <div>
            <p className="flex items-center gap-1 text-xs font-semibold text-red-500 mb-2">
              <Minus className="h-3 w-3" /> Dropped Keywords
            </p>
            <div className="flex flex-wrap gap-1">
              {kw.removed.map((k) => (
                <span key={k} className="px-2 py-0.5 rounded-full text-xs bg-red-500/10 text-red-500">
                  {k}
                </span>
              ))}
            </div>
          </div>
        )}
        {kw.common.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-muted-foreground mb-2">Unchanged</p>
            <div className="flex flex-wrap gap-1">
              {kw.common.map((k) => (
                <span key={k} className="px-2 py-0.5 rounded-full text-xs bg-accent text-accent-foreground">
                  {k}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────

export function ComparisonView({ session }: ComparisonViewProps) {
  const versions = buildVersionOptions(session);
  const [baseVer, setBaseVer] = useState<number | null>(null);
  const [targetVer, setTargetVer] = useState<number | null>(null);
  const compareAnalysis = useCompareAnalysis();
  const [result, setResult] = useState<ComparisonResult | null>(null);

  // Need at least 2 versions to compare
  if (versions.filter((v) => v.hasPosts).length < 2) {
    return (
      <div className="flex items-center justify-center h-48 text-muted-foreground text-sm">
        <GitCompare className="h-5 w-5 mr-2" />
        Need at least 2 completed versions to compare. Run a refresh to create v2.
      </div>
    );
  }

  const handleCompare = () => {
    if (baseVer == null || targetVer == null) return;
    compareAnalysis.mutate(
      {
        base: { session_id: session.id, version: baseVer },
        target: { session_id: session.id, version: targetVer },
      },
      {
        onSuccess: (data) => setResult(data),
      },
    );
  };

  return (
    <div className="space-y-6">
      {/* Version selector bar */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-muted-foreground">Base:</label>
          <select
            value={baseVer ?? ""}
            onChange={(e) => {
              setBaseVer(e.target.value ? Number(e.target.value) : null);
              setResult(null);
            }}
            className="px-2 py-1 rounded-md border border-border bg-background text-sm"
          >
            <option value="">Select version</option>
            {versions.filter((v) => v.hasPosts).map((v) => (
              <option key={v.version} value={v.version}>{v.label}</option>
            ))}
          </select>
        </div>

        <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />

        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-muted-foreground">Target:</label>
          <select
            value={targetVer ?? ""}
            onChange={(e) => {
              setTargetVer(e.target.value ? Number(e.target.value) : null);
              setResult(null);
            }}
            className="px-2 py-1 rounded-md border border-border bg-background text-sm"
          >
            <option value="">Select version</option>
            {versions.filter((v) => v.hasPosts).map((v) => (
              <option key={v.version} value={v.version}>{v.label}</option>
            ))}
          </select>
        </div>

        <button
          onClick={handleCompare}
          disabled={baseVer == null || targetVer == null || baseVer === targetVer || compareAnalysis.isPending}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium",
            "bg-primary text-primary-foreground",
            "hover:bg-primary/90 transition-colors",
            "disabled:opacity-50 disabled:cursor-not-allowed",
          )}
        >
          {compareAnalysis.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <GitCompare className="h-3.5 w-3.5" />
          )}
          Compare
        </button>

        {result && (
          <button
            onClick={() => setResult(null)}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Error */}
      {compareAnalysis.isError && (
        <div className="text-sm text-destructive">
          {compareAnalysis.error?.message || "Comparison failed"}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-4 animate-in fade-in-50 slide-in-from-top-2">
          {/* Narrative + Direction */}
          <div className="rounded-lg border border-border bg-card p-4">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm leading-relaxed">{result.narrative}</p>
              <DirectionBadge direction={result.sentiment.direction} />
            </div>
          </div>

          {/* Delta cards */}
          <SentimentDeltaCards comparison={result} />

          {/* Platform shifts */}
          <PlatformComparison comparison={result} />

          {/* Keywords */}
          <KeywordChanges comparison={result} />
        </div>
      )}
    </div>
  );
}
