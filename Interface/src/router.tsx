/**
 * TanStack Router configuration — code-based routing.
 *
 * Routes:
 *   /               → Home (new session / topic input)
 *   /session/$id    → Session view (chat + dashboard)
 */

import {
  createRouter,
  createRootRoute,
  createRoute,
  Outlet,
} from "@tanstack/react-router";
import { AppLayout } from "./components/layout/app-layout";
import { HomePage } from "./pages/home";
import { SessionPage } from "./pages/session";

// ── Root Route ────────────────────────────────────────────────────────

const rootRoute = createRootRoute({
  component: () => (
    <AppLayout>
      <Outlet />
    </AppLayout>
  ),
});

// ── Child Routes ──────────────────────────────────────────────────────

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: HomePage,
});

const sessionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/session/$sessionId",
  component: SessionPage,
});

// ── Router ────────────────────────────────────────────────────────────

const routeTree = rootRoute.addChildren([indexRoute, sessionRoute]);

export const router = createRouter({ routeTree });

// ── Type Registration ─────────────────────────────────────────────────

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
