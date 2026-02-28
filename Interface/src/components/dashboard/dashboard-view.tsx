/**
 * DashboardView — main dashboard layout after analysis completes.
 *
 * Layout:
 *   ┌──────────────────────────────────────────┐
 *   │  Stats Cards (4 across)                   │
 *   ├─────────────────────┬────────────────────┤
 *   │  Sentiment Chart    │  Platform Chart     │
 *   ├─────────────────────┴────────────────────┤
 *   │  Timeline Chart                           │
 *   ├──────────────────────────────────────────┤
 *   │  Filter Bar                               │
 *   ├──────────────────────────────────────────┤
 *   │  Posts Data Table                         │
 *   └──────────────────────────────────────────┘
 */

import { useState } from "react";
import type { AnalysisResult, DashboardFilters } from "@/lib/types";
import { StatsCards } from "./stats-cards";
import { SentimentPieChart } from "./sentiment-chart";
import { PlatformBarChart } from "./platform-chart";
import { TimelineChart } from "./timeline-chart";
import { FilterBar } from "./filter-bar";
import { PostsTable } from "./data-table";
import { KeywordCloud } from "./keyword-cloud";

interface DashboardViewProps {
  result: AnalysisResult;
}

const DEFAULT_FILTERS: DashboardFilters = {
  platforms: [],
  sentimentRange: [-1, 1],
  dateRange: null,
  searchQuery: "",
};

export function DashboardView({ result }: DashboardViewProps) {
  const [filters, setFilters] = useState<DashboardFilters>(DEFAULT_FILTERS);

  // Apply filters to posts
  const filteredPosts = result.posts.filter((post) => {
    // Platform filter
    if (
      filters.platforms.length > 0 &&
      !filters.platforms.includes(post.platform)
    )
      return false;

    // Sentiment range filter
    if (
      post.sentiment.compound < filters.sentimentRange[0] ||
      post.sentiment.compound > filters.sentimentRange[1]
    )
      return false;

    // Search query filter
    if (
      filters.searchQuery &&
      !post.content.toLowerCase().includes(filters.searchQuery.toLowerCase()) &&
      !post.author.toLowerCase().includes(filters.searchQuery.toLowerCase())
    )
      return false;

    return true;
  });

  return (
    <div className="h-full overflow-y-auto">
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        {/* Header */}
        <div>
          <h2 className="text-2xl font-bold">{result.topic}</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Analysed {result.summary.total_posts} posts across{" "}
            {result.platforms.length} platforms
          </p>
        </div>

        {/* Stats Cards */}
        <StatsCards summary={result.summary} />

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <SentimentPieChart summary={result.summary} />
          <PlatformBarChart platforms={result.platforms} />
        </div>

        {/* Timeline */}
        <TimelineChart data={result.summary.sentiment_over_time} />

        {/* Keywords */}
        <KeywordCloud keywords={result.summary.top_keywords} />

        {/* Filter + Data Table */}
        <FilterBar
          filters={filters}
          onFiltersChange={setFilters}
          platforms={result.platforms.map((p) => p.platform)}
          totalPosts={result.posts.length}
          filteredCount={filteredPosts.length}
        />

        <PostsTable posts={filteredPosts} />
      </div>
    </div>
  );
}
