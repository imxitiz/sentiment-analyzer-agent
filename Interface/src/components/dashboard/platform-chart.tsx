/**
 * PlatformBarChart — bar chart comparing sentiment across platforms.
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PlatformBreakdown } from "@/lib/types";
import { platformIcon } from "@/lib/types";

interface PlatformBarChartProps {
  platforms: PlatformBreakdown[];
}

export function PlatformBarChart({ platforms }: PlatformBarChartProps) {
  const data = platforms.map((p) => ({
    platform: `${platformIcon(p.platform)} ${p.platform}`,
    Positive: p.positive_pct,
    Neutral: p.neutral_pct,
    Negative: p.negative_pct,
    posts: p.post_count,
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Platform Comparison</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" barGap={2}>
              <CartesianGrid
                strokeDasharray="3 3"
                horizontal={false}
                stroke="hsl(var(--border))"
              />
              <XAxis
                type="number"
                domain={[0, 100]}
                tick={{ fontSize: 11 }}
                stroke="hsl(var(--muted-foreground))"
              />
              <YAxis
                type="category"
                dataKey="platform"
                width={120}
                tick={{ fontSize: 11 }}
                stroke="hsl(var(--muted-foreground))"
              />
              <Tooltip
                formatter={(value) => `${Number(value).toFixed(1)}%`}
                contentStyle={{
                  borderRadius: "8px",
                  border: "1px solid hsl(var(--border))",
                  backgroundColor: "hsl(var(--card))",
                  color: "hsl(var(--card-foreground))",
                }}
              />
              <Legend />
              <Bar
                dataKey="Positive"
                fill="#10b981"
                stackId="stack"
                radius={[0, 0, 0, 0]}
              />
              <Bar
                dataKey="Neutral"
                fill="#94a3b8"
                stackId="stack"
              />
              <Bar
                dataKey="Negative"
                fill="#ef4444"
                stackId="stack"
                radius={[0, 4, 4, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
