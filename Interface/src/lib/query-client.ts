/**
 * TanStack Query client configuration.
 *
 * Centralised QueryClient with sensible defaults for the dashboard:
 *   • Stale time: 30s (sessions update frequently)
 *   • Retry: 2 attempts
 *   • Refetch on window focus (catch updates while tabbed away)
 */

import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 2,
      refetchOnWindowFocus: true,
    },
    mutations: {
      retry: 1,
    },
  },
});
