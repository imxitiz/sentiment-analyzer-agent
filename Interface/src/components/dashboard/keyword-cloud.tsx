/**
 * KeywordCloud — visual display of top keywords.
 *
 * Simple weighted keyword display (not a true word cloud, but
 * visually effective and doesn't need a heavy library).
 */

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface KeywordCloudProps {
  keywords: string[];
}

export function KeywordCloud({ keywords }: KeywordCloudProps) {
  if (keywords.length === 0) return null;

  // Weight decreases with position
  const maxWeight = keywords.length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Top Keywords</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-2">
          {keywords.map((keyword, idx) => {
            const weight = (maxWeight - idx) / maxWeight;
            const fontSize = 0.75 + weight * 0.75; // 0.75rem to 1.5rem
            const opacity = 0.4 + weight * 0.6;

            return (
              <span
                key={keyword}
                className="inline-flex items-center px-3 py-1 rounded-full bg-primary/10 text-primary font-medium transition-all hover:bg-primary/20"
                style={{
                  fontSize: `${fontSize}rem`,
                  opacity,
                }}
              >
                {keyword}
              </span>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
