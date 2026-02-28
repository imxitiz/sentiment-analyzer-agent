/**
 * FilterBar — dashboard filters for platform, sentiment range, and search.
 */

import { Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { DashboardFilters } from "@/lib/types";
import { platformIcon } from "@/lib/types";
import { cn } from "@/lib/utils";

interface FilterBarProps {
  filters: DashboardFilters;
  onFiltersChange: (filters: DashboardFilters) => void;
  platforms: string[];
  totalPosts: number;
  filteredCount: number;
}

export function FilterBar({
  filters,
  onFiltersChange,
  platforms,
  totalPosts,
  filteredCount,
}: FilterBarProps) {
  const togglePlatform = (platform: string) => {
    const current = filters.platforms;
    const next = current.includes(platform)
      ? current.filter((p) => p !== platform)
      : [...current, platform];
    onFiltersChange({ ...filters, platforms: next });
  };

  const setSentimentFilter = (range: [number, number]) => {
    onFiltersChange({ ...filters, sentimentRange: range });
  };

  const setSearch = (query: string) => {
    onFiltersChange({ ...filters, searchQuery: query });
  };

  const clearFilters = () => {
    onFiltersChange({
      platforms: [],
      sentimentRange: [-1, 1],
      dateRange: null,
      searchQuery: "",
    });
  };

  const hasFilters =
    filters.platforms.length > 0 ||
    filters.sentimentRange[0] !== -1 ||
    filters.sentimentRange[1] !== 1 ||
    filters.searchQuery !== "";

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">
          Posts{" "}
          <span className="text-muted-foreground font-normal">
            {filteredCount === totalPosts
              ? `(${totalPosts})`
              : `(${filteredCount} of ${totalPosts})`}
          </span>
        </h3>
        {hasFilters && (
          <Button
            variant="ghost"
            size="sm"
            onClick={clearFilters}
            className="gap-1 text-xs"
          >
            <X className="h-3 w-3" />
            Clear filters
          </Button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {/* Platform filters */}
        <div className="flex items-center gap-1.5">
          {platforms.map((platform) => (
            <button
              key={platform}
              onClick={() => togglePlatform(platform)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-colors",
                filters.platforms.includes(platform)
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:bg-accent",
              )}
            >
              <span>{platformIcon(platform)}</span>
              {platform}
            </button>
          ))}
        </div>

        {/* Sentiment quick filters */}
        <div className="flex items-center gap-1.5">
          {[
            { label: "All", range: [-1, 1] as [number, number] },
            { label: "Positive", range: [0.2, 1] as [number, number] },
            { label: "Neutral", range: [-0.2, 0.2] as [number, number] },
            { label: "Negative", range: [-1, -0.2] as [number, number] },
          ].map(({ label, range }) => {
            const isActive =
              filters.sentimentRange[0] === range[0] &&
              filters.sentimentRange[1] === range[1];
            return (
              <button
                key={label}
                onClick={() => setSentimentFilter(range)}
                className={cn(
                  "px-3 py-1.5 rounded-full text-xs font-medium border transition-colors",
                  isActive
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:bg-accent",
                )}
              >
                {label}
              </button>
            );
          })}
        </div>

        {/* Search */}
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            value={filters.searchQuery}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search posts..."
            className="pl-9 h-8 text-xs"
          />
        </div>
      </div>
    </div>
  );
}
