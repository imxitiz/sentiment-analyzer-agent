/**
 * PostsTable — data table showing individual analysed posts with sentiment.
 *
 * Features:
 *   • Sortable columns (sentiment, date, platform)
 *   • Sentiment colour coding
 *   • Platform badges
 *   • Expandable content
 */

import { useState } from "react";
import { ArrowUpDown, ExternalLink, ChevronDown, ChevronUp } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import {
  sentimentLabel,
  sentimentColor,
  platformIcon,
  type AnalysedPost,
} from "@/lib/types";
import { cn } from "@/lib/utils";

interface PostsTableProps {
  posts: AnalysedPost[];
}

type SortKey = "sentiment" | "timestamp" | "platform";
type SortDir = "asc" | "desc";

export function PostsTable({ posts }: PostsTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("sentiment");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
    setPage(0);
  };

  const sorted = [...posts].sort((a, b) => {
    const dir = sortDir === "asc" ? 1 : -1;
    switch (sortKey) {
      case "sentiment":
        return (a.sentiment.compound - b.sentiment.compound) * dir;
      case "timestamp":
        return (
          (new Date(a.timestamp).getTime() -
            new Date(b.timestamp).getTime()) *
          dir
        );
      case "platform":
        return a.platform.localeCompare(b.platform) * dir;
      default:
        return 0;
    }
  });

  const pageCount = Math.ceil(sorted.length / pageSize);
  const paginated = sorted.slice(page * pageSize, (page + 1) * pageSize);

  const SortButton = ({
    label,
    sortKeyName,
  }: {
    label: string;
    sortKeyName: SortKey;
  }) => (
    <button
      onClick={() => toggleSort(sortKeyName)}
      className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
    >
      {label}
      <ArrowUpDown className="h-3 w-3" />
    </button>
  );

  if (posts.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground text-sm">
          No posts match the current filters.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-0">
        {/* Header */}
        <div className="grid grid-cols-[1fr_100px_100px_80px] gap-4 px-4 py-3 border-b border-border bg-muted/30">
          <span className="text-xs font-medium text-muted-foreground">
            Content
          </span>
          <SortButton label="Platform" sortKeyName="platform" />
          <SortButton label="Sentiment" sortKeyName="sentiment" />
          <SortButton label="Date" sortKeyName="timestamp" />
        </div>

        {/* Rows */}
        <div className="divide-y divide-border">
          {paginated.map((post) => {
            const isExpanded = expandedId === post.id;
            return (
              <div key={post.id} className="group">
                <div
                  className="grid grid-cols-[1fr_100px_100px_80px] gap-4 px-4 py-3 cursor-pointer hover:bg-muted/30 transition-colors items-center"
                  onClick={() =>
                    setExpandedId(isExpanded ? null : post.id)
                  }
                >
                  {/* Content */}
                  <div className="min-w-0">
                    <p
                      className={cn(
                        "text-sm leading-snug",
                        !isExpanded && "line-clamp-2",
                      )}
                    >
                      {post.content}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      by {post.author}
                    </p>
                  </div>

                  {/* Platform */}
                  <div className="flex items-center gap-1.5">
                    <span>{platformIcon(post.platform)}</span>
                    <span className="text-xs">{post.platform}</span>
                  </div>

                  {/* Sentiment */}
                  <div>
                    <span
                      className={cn(
                        "text-sm font-mono font-medium",
                        sentimentColor(post.sentiment.compound),
                      )}
                    >
                      {post.sentiment.compound > 0 ? "+" : ""}
                      {post.sentiment.compound.toFixed(3)}
                    </span>
                    <p className="text-xs text-muted-foreground">
                      {sentimentLabel(post.sentiment.compound)}
                    </p>
                  </div>

                  {/* Date */}
                  <div className="text-xs text-muted-foreground">
                    {new Date(post.timestamp).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    })}
                  </div>
                </div>

                {/* Expanded details */}
                {isExpanded && (
                  <div className="px-4 pb-4 space-y-2 bg-muted/10">
                    <div className="flex flex-wrap gap-1.5">
                      {post.keywords.map((kw) => (
                        <span
                          key={kw}
                          className="px-2 py-0.5 rounded-full bg-muted text-xs"
                        >
                          {kw}
                        </span>
                      ))}
                    </div>
                    <div className="flex gap-4 text-xs text-muted-foreground">
                      <span>
                        Pos: {(post.sentiment.positive * 100).toFixed(1)}%
                      </span>
                      <span>
                        Neu: {(post.sentiment.neutral * 100).toFixed(1)}%
                      </span>
                      <span>
                        Neg: {(post.sentiment.negative * 100).toFixed(1)}%
                      </span>
                    </div>
                    {post.url && (
                      <a
                        href={post.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                      >
                        View original
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Pagination */}
        {pageCount > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-border">
            <p className="text-xs text-muted-foreground">
              Page {page + 1} of {pageCount}
            </p>
            <div className="flex gap-1.5">
              <button
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
                className="px-3 py-1.5 rounded border border-border text-xs hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <button
                onClick={() => setPage(Math.min(pageCount - 1, page + 1))}
                disabled={page >= pageCount - 1}
                className="px-3 py-1.5 rounded border border-border text-xs hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
