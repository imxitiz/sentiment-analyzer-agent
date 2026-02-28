/**
 * ChatView — the complete chat experience for a session.
 *
 * Displays:
 *   • Conversation messages (user + assistant)
 *   • Real-time agent progress events
 *   • Topic input (for idle sessions)
 *   • Message input (for completed sessions — chat with data)
 */

import { useRef, useEffect } from "react";
import type { AgentEvent, Session } from "@/lib/types";
import { isSessionActive } from "@/lib/types";
import { ChatInput } from "./chat-input";
import { MessageBubble } from "./message-bubble";
import { AgentProgress } from "./agent-progress";

interface ChatViewProps {
  session: Session;
  events: AgentEvent[];
}

export function ChatView({ session, events }: ChatViewProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages/events
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [session.messages.length, events.length]);

  const showTopicInput = session.status === "idle" && !session.topic;
  const showMessageInput = session.status === "completed";
  const showProgress = isSessionActive(session.status) && events.length > 0;

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {/* Empty state */}
        {session.messages.length === 0 && events.length === 0 && (
          <div className="flex-1 flex items-center justify-center min-h-[400px]">
            <div className="text-center space-y-3 max-w-md">
              <div className="text-4xl">🔍</div>
              <h3 className="text-lg font-semibold">Start an Analysis</h3>
              <p className="text-sm text-muted-foreground">
                Enter a topic below to begin sentiment analysis. The AI will
                plan the research, collect data from multiple platforms, and
                generate insights.
              </p>
            </div>
          </div>
        )}

        {/* Messages */}
        {session.messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {/* Agent Progress */}
        {showProgress && <AgentProgress events={events} status={session.status} />}
      </div>

      {/* Input area */}
      <div className="shrink-0 border-t border-border p-4">
        <ChatInput
          sessionId={session.id}
          sessionStatus={session.status}
          topic={session.topic}
        />
      </div>
    </div>
  );
}
