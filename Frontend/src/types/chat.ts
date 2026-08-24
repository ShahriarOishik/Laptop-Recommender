import type { Laptop, LaptopFilters, LaptopRecommendation, RetrievedEvidence } from "./laptop";
import type { ApiIndexType, ChatIntent } from "./api";

export interface RecommendationRequest {
  query: string;
  filters?: LaptopFilters;
  top_k?: number;
  indexType?: ApiIndexType;
  groundingLaptopIds?: string[];
  /** Backend conversation id — omit on the first message of a session so
   * the backend starts a new conversation and returns its id. */
  conversationId?: string;
  /** True only when the user explicitly ran "/suggest" this turn. */
  forceRetrieval?: boolean;
}

export interface RagDebugInfo {
  query: string;
  filters?: LaptopFilters;
  embeddingModel?: string;
  faissIndexType?: string;
  topK?: number;
  retrievedIds?: string[];
  retrievalLatencyMs?: number;
  generationLatencyMs?: number;
  totalLatencyMs?: number;
}

export interface RecommendationResponse {
  answer: string;
  recommendations: LaptopRecommendation[];
  retrievedContext: RetrievedEvidence[];
  hasExactMatches?: boolean;
  /** Explains a filter the backend relaxed to avoid an empty result (e.g.
   * "includes options slightly over budget"). Null/absent when nothing
   * was relaxed. */
  message?: string | null;
  /** Names of filters the backend relaxed for this response, e.g.
   * ["price_range"]. Empty when nothing was relaxed. */
  relaxedFilters?: string[];
  debug?: RagDebugInfo;
  /** Conversation-aware fields — populated for the real backend, absent
   * in mock mode (mock responses are always treated as new_recommendation). */
  conversationId?: string;
  intent?: ChatIntent;
  referencedLaptopIds?: string[];
}

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  text?: string;
  recommendations?: LaptopRecommendation[];
  retrievedContext?: RetrievedEvidence[];
  hasExactMatches?: boolean;
  requestQuery?: string;
  requestFilters?: LaptopFilters;
  /** Mirrors the request that produced this turn, so Retry re-issues the
   * same kind of request (a /suggest search vs. plain chat). */
  requestForceRetrieval?: boolean;
  requestIndexType?: ApiIndexType;
  requestTopK?: number;
  /** True on a user message that was sent via the "/suggest" command. */
  isCommand?: boolean;
  /** Recommendation cards have rendered (streaming) but the narrative
   * answer text hasn't arrived yet — shows a small "writing…" indicator
   * instead of leaving the message looking finished-but-blank. */
  isAnswerPending?: boolean;
  message?: string | null;
  relaxedFilters?: string[];
  debug?: RagDebugInfo;
  intent?: ChatIntent;
  referencedLaptopIds?: string[];
  isLoading?: boolean;
  isError?: boolean;
  createdAt: number;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  /** Backend conversation id, set once the first response comes back. */
  conversationId?: string;
}

export interface CompareLaptop {
  laptop: Laptop;
  matchScore?: number;
}
