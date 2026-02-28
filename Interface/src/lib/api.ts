/**
 * API client — typed HTTP client for the Python FastAPI backend.
 *
 * All API calls go through this module. The base URL is configurable
 * via the `API_BASE_URL` constant (defaults to `http://localhost:8000`).
 *
 * Usage:
 *   import { api } from "@/lib/api";
 *   const sessions = await api.sessions.list();
 *   const session = await api.sessions.create({ topic: "Nepal elections" });
 */

import type {
  CreateSessionRequest,
  SendMessageRequest,
  Session,
  SessionDetailResponse,
  SessionListResponse,
  StartAnalysisRequest,
} from "./types";

// ── Configuration ─────────────────────────────────────────────────────

export const API_BASE_URL =
  typeof window !== "undefined"
    ? (window as any).__API_BASE_URL ?? "http://localhost:8000"
    : "http://localhost:8000";

export const WS_BASE_URL = API_BASE_URL.replace(/^http/, "ws");

// ── HTTP helpers ──────────────────────────────────────────────────────

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "Unknown error");
    throw new Error(`API ${res.status}: ${body}`);
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Session API ───────────────────────────────────────────────────────

export const api = {
  health: () => fetchJSON<{ status: string }>("/api/health"),

  sessions: {
    /** List all sessions (most recent first). */
    list: () =>
      fetchJSON<SessionListResponse>("/api/sessions").then((r) => r.sessions),

    /** Create a new analysis session. */
    create: (req: CreateSessionRequest = {}) =>
      fetchJSON<{ session: Session }>("/api/sessions", {
        method: "POST",
        body: JSON.stringify(req),
      }).then((r) => r.session),

    /** Get a single session by ID. */
    get: (id: string) =>
      fetchJSON<SessionDetailResponse>(`/api/sessions/${id}`).then(
        (r) => r.session,
      ),

    /** Delete a session. */
    delete: (id: string) =>
      fetchJSON<void>(`/api/sessions/${id}`, { method: "DELETE" }),

    /** Start analysis for a session. */
    start: (id: string, req: StartAnalysisRequest) =>
      fetchJSON<SessionDetailResponse>(`/api/sessions/${id}/start`, {
        method: "POST",
        body: JSON.stringify(req),
      }).then((r) => r.session),

    /** Refresh (re-run) analysis for a completed session. */
    refresh: (id: string) =>
      fetchJSON<SessionDetailResponse>(`/api/sessions/${id}/refresh`, {
        method: "POST",
      }).then((r) => r.session),

    /** Switch active version for a session. */
    switchVersion: (id: string, version: number) =>
      fetchJSON<SessionDetailResponse>(`/api/sessions/${id}/version`, {
        method: "POST",
        body: JSON.stringify({ version }),
      }).then((r) => r.session),

    /** Send a message to a session. */
    sendMessage: (id: string, req: SendMessageRequest) =>
      fetchJSON<SessionDetailResponse>(`/api/sessions/${id}/messages`, {
        method: "POST",
        body: JSON.stringify(req),
      }).then((r) => r.session),
  },
} as const;
