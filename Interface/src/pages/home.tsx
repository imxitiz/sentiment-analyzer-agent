/**
 * Home page — displayed when no session is selected.
 *
 * Shows a welcoming UI with a quick-start topic input that creates
 * a new session and starts analysis immediately.
 */

import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { Activity, ArrowRight, Sparkles, BarChart3, Globe, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCreateSession, useStartAnalysis } from "@/hooks/use-sessions";

const SUGGESTED_TOPICS = [
  "Nepal elections 2026",
  "AI regulation debate",
  "Electric vehicles adoption",
  "Climate change policy",
  "Cryptocurrency market",
  "Remote work trends",
];

export function HomePage() {
  const [topic, setTopic] = useState("");
  const navigate = useNavigate();
  const createSession = useCreateSession();
  const startAnalysis = useStartAnalysis();

  const handleSubmit = async (topicText: string) => {
    if (!topicText.trim()) return;

    try {
      // Create session and start analysis in one flow
      const session = await createSession.mutateAsync({
        topic: topicText.trim(),
      });

      // Navigate immediately — analysis will start
      navigate({
        to: "/session/$sessionId",
        params: { sessionId: session.id },
      });

      // Start analysis in background
      startAnalysis.mutate({
        sessionId: session.id,
        topic: topicText.trim(),
        llm_provider: "dummy",
      });
    } catch {
      // Error handled by query
    }
  };

  const isSubmitting = createSession.isPending || startAnalysis.isPending;

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8">
      <div className="max-w-2xl w-full text-center space-y-8">
        {/* Hero */}
        <div className="space-y-4">
          <div className="flex items-center justify-center gap-3 mb-6">
            <Activity className="h-10 w-10 text-primary" />
            <h1 className="text-4xl font-bold tracking-tight">
              Sentiment Analyzer
            </h1>
          </div>
          <p className="text-lg text-muted-foreground max-w-lg mx-auto">
            AI-powered sentiment analysis pipeline. Enter a topic and get
            real-time insights from across the web.
          </p>
        </div>

        {/* Feature badges */}
        <div className="flex flex-wrap items-center justify-center gap-3">
          {[
            { icon: Globe, label: "Multi-platform" },
            { icon: Sparkles, label: "AI-powered" },
            { icon: BarChart3, label: "Real-time dashboard" },
            { icon: MessageSquare, label: "Chat with data" },
          ].map(({ icon: Icon, label }) => (
            <div
              key={label}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-muted text-muted-foreground text-sm"
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </div>
          ))}
        </div>

        {/* Topic Input */}
        <div className="space-y-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSubmit(topic);
            }}
            className="flex gap-2"
          >
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="Enter a topic to analyse... (e.g., Nepal elections 2026)"
              className="flex-1 px-4 py-3 rounded-lg border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              disabled={isSubmitting}
              autoFocus
            />
            <Button
              type="submit"
              size="lg"
              disabled={!topic.trim() || isSubmitting}
              className="gap-2"
            >
              Analyse
              <ArrowRight className="h-4 w-4" />
            </Button>
          </form>

          {/* Suggested Topics */}
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">Try a suggested topic:</p>
            <div className="flex flex-wrap gap-2 justify-center">
              {SUGGESTED_TOPICS.map((t) => (
                <button
                  key={t}
                  onClick={() => handleSubmit(t)}
                  disabled={isSubmitting}
                  className="px-3 py-1.5 rounded-full border border-border text-sm hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50"
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
