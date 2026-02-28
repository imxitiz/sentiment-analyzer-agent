/**
 * SentimentPieChart — donut chart showing sentiment distribution.
 */

import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SentimentSummary } from "@/lib/types";

interface SentimentPieChartProps {
  summary: SentimentSummary;
}

const COLORS = {
  Positive: "#10b981",
  Neutral: "#94a3b8",
  Negative: "#ef4444",
};

export function SentimentPieChart({ summary }: SentimentPieChartProps) {
  const data = [
    { name: "Positive", value: summary.positive_pct, color: COLORS.Positive },
    { name: "Neutral", value: summary.neutral_pct, color: COLORS.Neutral },
    { name: "Negative", value: summary.negative_pct, color: COLORS.Negative },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Sentiment Distribution</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={100}
                paddingAngle={3}
                dataKey="value"
                label={({ name, value }) => `${name}: ${value.toFixed(1)}%`}
                labelLine={false}
              >
                {data.map((entry) => (
                  <Cell key={entry.name} fill={entry.color} />
                ))}
              </Pie>
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
            </PieChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
