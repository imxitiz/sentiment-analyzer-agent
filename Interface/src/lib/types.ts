/**
 * Shared TypeScript types — mirrors the Python Pydantic models in server/models.py
 *
 * These types define the exact shape of all API responses and WebSocket events.
 * Keep them in sync with the Python models.
 */

// ── Enums ─────────────────────────────────────────────────────────────

export type SessionStatus =
  | "idle"
  | "planning"
  | "searching"
  | "scraping"
  | "cleaning"
  | "analysing"
  | "clarification_needed"
  | "completed"
  | "error";

export type MessageRole = "user" | "assistant" | "system";

export type AgentEventType =
  | "agent_start"
  | "agent_progress"
  | "agent_complete"
  | "clarification_needed"
  | "pipeline_complete"
  | "status_change"
  | "error";

// ── Chat Messages ─────────────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
  metadata: Record<string, unknown>;
}

// ── Agent Events (WebSocket) ─────────────────────────────────────────

export interface AgentEvent {
  type: AgentEventType;
  agent: string;
  message: string;
  data: Record<string, unknown>;
  timestamp: string;
}

// ── Sentiment ─────────────────────────────────────────────────────────

export interface SentimentScore {
  positive: number;
  negative: number;
  neutral: number;
  compound: number;
}

export interface AnalysedPost {
  id: string;
  platform: string;
  author: string;
  content: string;
  url: string;
  sentiment: SentimentScore;
  keywords: string[];
  timestamp: string;
  metadata: Record<string, unknown>;
}

export interface PlatformBreakdown {
  platform: string;
  post_count: number;
  avg_sentiment: number;
  positive_pct: number;
  negative_pct: number;
  neutral_pct: number;
  top_keywords: string[];
}

export interface SentimentSummary {
  total_posts: number;
  avg_compound: number;
  positive_pct: number;
  negative_pct: number;
  neutral_pct: number;
  most_positive_post: string;
  most_negative_post: string;
  top_keywords: string[];
  sentiment_over_time: Array<{
    date: string;
    avg_sentiment: number;
    post_count: number;
    positive: number;
    negative: number;
    neutral: number;
  }>;
}

export interface ResearchPlanData {
  topic_summary: string;
  keywords: string[];
  hashtags: string[];
  platforms: Array<{ name: string; priority: string; reason: string }>;
  search_queries: string[];
  estimated_volume: string;
  reasoning: string;
}

export interface AnalysisResult {
  topic: string;
  plan: ResearchPlanData | null;
  summary: SentimentSummary;
  posts: AnalysedPost[];
  platforms: PlatformBreakdown[];
  completed_at: string;
}

// ── Session ───────────────────────────────────────────────────────────

export interface Session {
  id: string;
  topic: string | null;
  status: SessionStatus;
  version: number;
  messages: ChatMessage[];
  events: AgentEvent[];
  result: AnalysisResult | null;
  llm_provider: string;
  created_at: string;
  updated_at: string;
}

// ── API Request/Response ──────────────────────────────────────────────

export interface CreateSessionRequest {
  topic?: string;
  llm_provider?: string;
  llm_model?: string;
}

export interface StartAnalysisRequest {
  topic: string;
  llm_provider?: string;
  llm_model?: string;
}

export interface SendMessageRequest {
  content: string;
}

export interface SessionListResponse {
  sessions: Session[];
}

export interface SessionDetailResponse {
  session: Session;
}

export interface VersionListResponse {
  current_version: number;
  versions: VersionSnapshot[];
}

// ── UI State ──────────────────────────────────────────────────────────

export type ViewMode = "chat" | "dashboard";

export interface SessionUIState {
  viewMode: ViewMode;
  dashboardFilters: DashboardFilters;
}

export interface DashboardFilters {
  platforms: string[];
  sentimentRange: [number, number];
  dateRange: [string, string] | null;
  searchQuery: string;
}

// ── Helpers ───────────────────────────────────────────────────────────

export const SESSION_STATUS_LABELS: Record<SessionStatus, string> = {
  idle: "Ready",
  planning: "Planning...",
  searching: "Searching...",
  scraping: "Scraping...",
  cleaning: "Cleaning...",
  analysing: "Analysing...",
  clarification_needed: "Needs Input",
  completed: "Complete",
  error: "Error",
};

export const ACTIVE_STATUSES: SessionStatus[] = [
  "planning",
  "searching",
  "scraping",
  "cleaning",
  "analysing",
];

export function isSessionActive(status: SessionStatus): boolean {
  return ACTIVE_STATUSES.includes(status);
}

export function sentimentLabel(compound: number): string {
  if (compound > 0.3) return "Positive";
  if (compound > 0.1) return "Slightly Positive";
  if (compound > -0.1) return "Neutral";
  if (compound > -0.3) return "Slightly Negative";
  return "Negative";
}

export function sentimentColor(compound: number): string {
  if (compound > 0.3) return "text-emerald-500";
  if (compound > 0.1) return "text-emerald-400";
  if (compound > -0.1) return "text-slate-400";
  if (compound > -0.3) return "text-red-400";
  return "text-red-500";
}

export function platformIcon(platform: string): string {
  const icons: Record<string, string> = {
    reddit: "🟠",
    twitter: "🐦",
    news: "📰",
    facebook: "📘",
    youtube: "▶️",
  };
  return icons[platform] ?? "🌐";
}
