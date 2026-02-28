/**
 * ChatInput — topic input for new sessions, message input for completed ones.
 *
 * Behaviour:
 *   • idle + no topic → "Enter a topic to analyse"
 *   • active → disabled with status label
 *   • completed → "Ask about the analysis..."
 *   • clarification_needed → "Respond to clarification..."
 */

import { useState } from "react";
import { Send, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useStartAnalysis, useSendMessage } from "@/hooks/use-sessions";
import {
  isSessionActive,
  SESSION_STATUS_LABELS,
  type SessionStatus,
} from "@/lib/types";

interface ChatInputProps {
  sessionId: string;
  sessionStatus: SessionStatus;
  topic: string | null;
}

export function ChatInput({ sessionId, sessionStatus, topic }: ChatInputProps) {
  const [input, setInput] = useState("");
  const startAnalysis = useStartAnalysis();
  const sendMessage = useSendMessage();

  const isActive = isSessionActive(sessionStatus);
  const isIdle = sessionStatus === "idle";
  const isCompleted = sessionStatus === "completed";
  const isClarification = sessionStatus === "clarification_needed";
  const isPending = startAnalysis.isPending || sendMessage.isPending;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isPending) return;

    const text = input.trim();
    setInput("");

    if (isIdle) {
      // Start new analysis
      startAnalysis.mutate({
        sessionId,
        topic: text,
        llm_provider: "dummy",
      });
    } else if (isCompleted || isClarification) {
      // Send follow-up message
      sendMessage.mutate({
        sessionId,
        content: text,
      });
    }
  };

  let placeholder = "Enter a topic to analyse...";
  if (isActive) placeholder = `${SESSION_STATUS_LABELS[sessionStatus]} Please wait...`;
  else if (isCompleted) placeholder = "Ask a question about the analysis...";
  else if (isClarification) placeholder = "Respond to the clarification request...";

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 items-end max-w-4xl mx-auto w-full">
      <div className="flex-1 relative">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
          placeholder={placeholder}
          disabled={isActive || isPending}
          rows={1}
          className="w-full resize-none px-4 py-3 rounded-lg border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] max-h-[120px]"
          style={{ height: "auto" }}
        />
      </div>
      <Button
        type="submit"
        size="icon"
        disabled={!input.trim() || isActive || isPending}
        className="h-[44px] w-[44px] shrink-0"
      >
        {isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Send className="h-4 w-4" />
        )}
      </Button>
    </form>
  );
}
