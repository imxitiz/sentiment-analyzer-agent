/**
 * MessageBubble — renders a single chat message.
 *
 * • User messages: right-aligned, primary colour
 * • Assistant messages: left-aligned, card style with markdown-ish rendering
 * • System messages: centered, muted
 */

import { Bot, User } from "lucide-react";
import type { ChatMessage } from "@/lib/types";
import { cn } from "@/lib/utils";

interface MessageBubbleProps {
  message: ChatMessage;
}

/** Very simple markdown-ish rendering (bold, newlines, bullet lists). */
function renderContent(content: string) {
  // Replace **text** with <strong>
  let html = content.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  // Replace *text* with <em>
  html = html.replace(/\*(.*?)\*/g, "<em>$1</em>");
  // Replace `code` with <code>
  html = html.replace(/`(.*?)`/g, '<code class="px-1 py-0.5 rounded bg-muted text-xs font-mono">$1</code>');
  // Replace newlines
  html = html.replace(/\n/g, "<br />");
  return html;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isClarificationRequest =
    message.role === "assistant" && message.metadata?.kind === "clarification_request";

  if (message.role === "system") {
    return (
      <div className="flex justify-center my-2">
        <div className="px-4 py-2 rounded-lg bg-muted/50 text-xs text-muted-foreground max-w-lg text-center">
          <span dangerouslySetInnerHTML={{ __html: renderContent(message.content) }} />
        </div>
      </div>
    );
  }

  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "flex gap-3 max-w-4xl",
        isUser ? "ml-auto flex-row-reverse" : "mr-auto",
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex items-center justify-center h-8 w-8 rounded-full shrink-0",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      {/* Bubble */}
      <div
        className={cn(
          "px-4 py-3 rounded-2xl text-sm leading-relaxed max-w-xl",
          isUser
            ? "bg-primary text-primary-foreground rounded-br-md"
            : isClarificationRequest
              ? "bg-amber-50 border border-amber-200 text-amber-950 rounded-bl-md dark:bg-amber-950/20 dark:border-amber-900 dark:text-amber-100"
              : "bg-card border border-border rounded-bl-md",
        )}
      >
        {isClarificationRequest && (
          <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-600 dark:text-amber-300">
            Clarification Needed
          </div>
        )}
        <span
          dangerouslySetInnerHTML={{ __html: renderContent(message.content) }}
        />
      </div>
    </div>
  );
}
