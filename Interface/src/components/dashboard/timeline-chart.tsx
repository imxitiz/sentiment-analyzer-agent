/**
 * TimelineChart — sentiment trend over time.
 */

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface TimelineChartProps {
  data: Array<{
    date: string;
    avg_sentiment: number;
    post_count: number;
    positive: number;
    negative: number;
    neutral: number;
  }>;
}

export function TimelineChart({ data }: TimelineChartProps) {
  if (data.length === 0) return null;

  const chartData = data.map((d) => ({
    ...d,
    date: new Date(d.date).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    }),
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Sentiment Over Time</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="sentimentGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                  <stop offset="50%" stopColor="#94a3b8" stopOpacity={0.1} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0.3} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="hsl(var(--border))"
              />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11 }}
                stroke="hsl(var(--muted-foreground))"
              />
              <YAxis
                domain={[-1, 1]}
                tick={{ fontSize: 11 }}
                stroke="hsl(var(--muted-foreground))"
                tickFormatter={(v: number) => v.toFixed(1)}
              />
              <Tooltip
                formatter={(value, name) => {
                  if (name === "avg_sentiment")
                    return [Number(value).toFixed(3), "Avg Sentiment"];
                  return [value, String(name)];
                }}
                contentStyle={{
                  borderRadius: "8px",
                  border: "1px solid hsl(var(--border))",
                  backgroundColor: "hsl(var(--card))",
                  color: "hsl(var(--card-foreground))",
                }}
              />
              <Area
                type="monotone"
                dataKey="avg_sentiment"
                stroke="#6366f1"
                strokeWidth={2}
                fill="url(#sentimentGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        {/* Post volume bar */}
        <div className="mt-4 flex items-end gap-1 h-12">
          {chartData.map((d, i) => {
            const maxCount = Math.max(...chartData.map((x) => x.post_count));
            const height = maxCount > 0 ? (d.post_count / maxCount) * 100 : 0;
            return (
              <div key={i} className="flex-1 flex flex-col items-center">
                <div
                  className="w-full bg-muted rounded-t transition-all"
                  style={{ height: `${height}%` }}
                  title={`${d.date}: ${d.post_count} posts`}
                />
              </div>
            );
          })}
        </div>
        <p className="text-xs text-muted-foreground text-center mt-1">
          Post volume per day
        </p>
      </CardContent>
    </Card>
  );
}
