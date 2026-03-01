/**
 * TanStack Query hooks for session data.
 *
 * These hooks handle all server state management:
 *   • useSessionList() — all sessions
 *   • useSession(id) — single session detail (auto-refetch when active)
 *   • useCreateSession() — create mutation
 *   • useStartAnalysis() — start analysis mutation
 *   • useSendMessage() — send message mutation
 *   • useDeleteSession() — delete mutation
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  CompareRequest,
  CreateSessionRequest,
  SendMessageRequest,
  Session,
  StartAnalysisRequest,
} from "@/lib/types";
import { isSessionActive } from "@/lib/types";

// ── Query Keys ────────────────────────────────────────────────────────

export const sessionKeys = {
  all: ["sessions"] as const,
  lists: () => [...sessionKeys.all, "list"] as const,
  detail: (id: string) => [...sessionKeys.all, "detail", id] as const,
};

// ── Queries ───────────────────────────────────────────────────────────

/** Fetch all sessions. */
export function useSessionList() {
  return useQuery({
    queryKey: sessionKeys.lists(),
    queryFn: () => api.sessions.list(),
  });
}

/** Fetch a single session with auto-refetch when analysis is running. */
export function useSession(id: string | undefined) {
  return useQuery({
    queryKey: sessionKeys.detail(id ?? ""),
    queryFn: () => api.sessions.get(id!),
    enabled: !!id,
    // Refetch every 2s while analysis is active
    refetchInterval: (query) => {
      const session = query.state.data;
      if (session && isSessionActive(session.status)) return 2000;
      return false;
    },
  });
}

// ── Mutations ─────────────────────────────────────────────────────────

/** Create a new session. */
export function useCreateSession() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (req: CreateSessionRequest) => api.sessions.create(req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: sessionKeys.lists() });
    },
  });
}

/** Start analysis for a session. */
export function useStartAnalysis() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({
      sessionId,
      ...req
    }: StartAnalysisRequest & { sessionId: string }) =>
      api.sessions.start(sessionId, req),
    onSuccess: (session) => {
      qc.setQueryData(sessionKeys.detail(session.id), session);
      qc.invalidateQueries({ queryKey: sessionKeys.lists() });
    },
  });
}

/** Send a message to a session. */
export function useSendMessage() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({
      sessionId,
      ...req
    }: SendMessageRequest & { sessionId: string }) =>
      api.sessions.sendMessage(sessionId, req),
    onSuccess: (session) => {
      qc.setQueryData(sessionKeys.detail(session.id), session);
    },
  });
}

/** Delete a session. */
export function useDeleteSession() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => api.sessions.delete(id),
    onSuccess: (_data, id) => {
      qc.removeQueries({ queryKey: sessionKeys.detail(id) });
      qc.invalidateQueries({ queryKey: sessionKeys.lists() });
    },
  });
}

/** Refresh (re-run) analysis for a completed session. */
export function useRefreshAnalysis() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (sessionId: string) => api.sessions.refresh(sessionId),
    onSuccess: (session) => {
      qc.setQueryData(sessionKeys.detail(session.id), session);
      qc.invalidateQueries({ queryKey: sessionKeys.lists() });
    },
  });
}

/** Switch to a different analysis version. */
export function useSwitchVersion() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ sessionId, version }: { sessionId: string; version: number }) =>
      api.sessions.switchVersion(sessionId, version),
    onSuccess: (session) => {
      qc.setQueryData(sessionKeys.detail(session.id), session);
      qc.invalidateQueries({ queryKey: sessionKeys.lists() });
    },
  });
}

/** Compare two analysis results (versions or sessions). */
export function useCompareAnalysis() {
  return useMutation({
    mutationFn: (req: CompareRequest) => api.compare(req),
  });
}
