/**
 * WebSocket manager — typed real-time connection to the backend.
 *
 * Handles:
 *   • Auto-reconnect with exponential backoff
 *   • Event replay on reconnect (server sends past events)
 *   • Typed event callbacks
 *
 * Usage:
 *   const ws = new SessionWebSocket("session-id", {
 *     onEvent: (event) => console.log(event),
 *     onStatusChange: (status) => console.log(status),
 *   });
 *   ws.connect();
 *   ws.disconnect();
 */

import type { AgentEvent, SessionStatus } from "./types";
import { WS_BASE_URL } from "./api";

export interface WSCallbacks {
  onEvent?: (event: AgentEvent) => void;
  onStatusChange?: (status: SessionStatus) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
}

export class SessionWebSocket {
  private ws: WebSocket | null = null;
  private sessionId: string;
  private callbacks: WSCallbacks;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private intentionalClose = false;

  constructor(sessionId: string, callbacks: WSCallbacks = {}) {
    this.sessionId = sessionId;
    this.callbacks = callbacks;
  }

  /** Open the WebSocket connection. */
  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    this.intentionalClose = false;
    const url = `${WS_BASE_URL}/ws/${this.sessionId}`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.callbacks.onOpen?.();
    };

    this.ws.onmessage = (evt) => {
      try {
        const event: AgentEvent = JSON.parse(evt.data);
        this.callbacks.onEvent?.(event);

        // Extract status changes
        if (event.type === "status_change" && event.data?.status) {
          this.callbacks.onStatusChange?.(
            event.data.status as SessionStatus,
          );
        }
      } catch {
        // Ignore malformed messages
      }
    };

    this.ws.onclose = () => {
      this.callbacks.onClose?.();
      if (!this.intentionalClose) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = (err) => {
      this.callbacks.onError?.(err);
    };
  }

  /** Gracefully close the connection (no reconnect). */
  disconnect(): void {
    this.intentionalClose = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  /** Send a message to the server. */
  send(data: { type: string; content?: string }): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  /** Whether the connection is currently open. */
  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  /** Update session ID (disconnects and reconnects). */
  setSessionId(id: string): void {
    this.disconnect();
    this.sessionId = id;
    this.reconnectAttempts = 0;
    this.connect();
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;

    const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 30000);
    this.reconnectAttempts++;

    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, delay);
  }
}
