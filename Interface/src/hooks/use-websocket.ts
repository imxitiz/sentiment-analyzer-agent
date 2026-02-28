/**
 * WebSocket hook — manages real-time connection for a session.
 *
 * Connects when sessionId changes, disconnects on unmount.
 * Collects events into a local array and provides connection status.
 *
 * Usage:
 *   const { events, isConnected } = useSessionWebSocket(sessionId);
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { SessionWebSocket } from "@/lib/ws";
import { sessionKeys } from "./use-sessions";
import type { AgentEvent, SessionStatus } from "@/lib/types";

export function useSessionWebSocket(sessionId: string | undefined) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [latestStatus, setLatestStatus] = useState<SessionStatus | null>(null);
  const wsRef = useRef<SessionWebSocket | null>(null);
  const qc = useQueryClient();

  const handleEvent = useCallback(
    (event: AgentEvent) => {
      setEvents((prev) => [...prev, event]);

      // When pipeline completes or status changes to completed, refetch session
      if (
        event.type === "pipeline_complete" ||
        (event.type === "status_change" && event.data?.status === "completed")
      ) {
        if (sessionId) {
          qc.invalidateQueries({
            queryKey: sessionKeys.detail(sessionId),
          });
          qc.invalidateQueries({ queryKey: sessionKeys.lists() });
        }
      }
    },
    [sessionId, qc],
  );

  const handleStatusChange = useCallback((status: SessionStatus) => {
    setLatestStatus(status);
  }, []);

  useEffect(() => {
    if (!sessionId) return;

    // Reset events when session changes
    setEvents([]);
    setLatestStatus(null);

    const ws = new SessionWebSocket(sessionId, {
      onEvent: handleEvent,
      onStatusChange: handleStatusChange,
      onOpen: () => setIsConnected(true),
      onClose: () => setIsConnected(false),
    });

    ws.connect();
    wsRef.current = ws;

    return () => {
      ws.disconnect();
      wsRef.current = null;
    };
  }, [sessionId, handleEvent, handleStatusChange]);

  const sendMessage = useCallback((content: string) => {
    wsRef.current?.send({ type: "user_message", content });
  }, []);

  return {
    events,
    isConnected,
    latestStatus,
    sendMessage,
  };
}
