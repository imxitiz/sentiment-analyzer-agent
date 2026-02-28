/**
 * StatsCards — summary statistics at the top of the dashboard.
 *
 * Shows 4 cards:
 *   • Total posts analysed
 *   • Average compound sentiment
 *   • Most common sentiment
 *   • Sentiment distribution (mini bar)
 */

import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  Hash,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { sentimentLabel, sentimentColor, type SentimentSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

interface StatsCardsProps {
  summary: SentimentSummary;
}

export function StatsCards({ summary }: StatsCardsProps) {
  const dominantSentiment =
    summary.positive_pct > summary.negative_pct
      ? summary.positive_pct > summary.neutral_pct
        ? "Positive"
        : "Neutral"
      : summary.negative_pct > summary.neutral_pct
        ? "Negative"
        : "Neutral";

  const cards = [
    {
      label: "Total Posts",
      value: summary.total_posts.toLocaleString(),
      subtext: `across all platforms`,
      icon: BarChart3,
      iconColor: "text-blue-500",
    },
    {
      label: "Average Sentiment",
      value: summary.avg_compound.toFixed(3),
      subtext: sentimentLabel(summary.avg_compound),
      icon: summary.avg_compound >= 0 ? TrendingUp : TrendingDown,
      iconColor: sentimentColor(summary.avg_compound),
    },
    {
      label: "Dominant Sentiment",
      value: dominantSentiment,
      subtext: `${Math.max(summary.positive_pct, summary.negative_pct, summary.neutral_pct).toFixed(1)}% of posts`,
      icon: TrendingUp,
      iconColor:
        dominantSentiment === "Positive"
          ? "text-emerald-500"
          : dominantSentiment === "Negative"
            ? "text-red-500"
            : "text-slate-400",
    },
    {
      label: "Top Keywords",
      value: summary.top_keywords.length.toString(),
      subtext: summary.top_keywords.slice(0, 3).join(", "),
      icon: Hash,
      iconColor: "text-violet-500",
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card) => (
        <Card key={card.label}>
          <CardContent className="pt-6">
            <div className="flex items-start justify-between">
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground">
                  {card.label}
                </p>
                <p className="text-2xl font-bold">{card.value}</p>
                <p className="text-xs text-muted-foreground">{card.subtext}</p>
              </div>
              <card.icon className={cn("h-5 w-5", card.iconColor)} />
            </div>

            {/* Mini sentiment bar for average sentiment card */}
            {card.label === "Average Sentiment" && (
              <div className="mt-3 flex h-2 rounded-full overflow-hidden bg-muted">
                <div
                  className="bg-emerald-500 transition-all"
                  style={{ width: `${summary.positive_pct}%` }}
                />
                <div
                  className="bg-slate-400 transition-all"
                  style={{ width: `${summary.neutral_pct}%` }}
                />
                <div
                  className="bg-red-500 transition-all"
                  style={{ width: `${summary.negative_pct}%` }}
                />
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
