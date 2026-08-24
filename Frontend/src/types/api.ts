/**
 * Raw backend DTOs — mirror `Backend/app/models.py` field-for-field
 * (snake_case, same optionality). These are never used directly by UI
 * components; `services/recommendationService.ts` and `services/
 * laptopService.ts` adapt them into the UI-facing types in `types/chat.ts`
 * and `types/laptop.ts`.
 */

export type ApiIndexType = "flat" | "ivf_flat" | "pq" | "ivf_pq" | "hnsw";
export type ApiLaptopCatalogSort = "name" | "price-asc" | "price-desc";

export type ChatIntent =
  | "new_recommendation"
  | "follow_up"
  | "updated_requirements"
  | "general_question";

export interface ApiSearchFilters {
  min_price_usd?: number | null;
  max_price_usd?: number | null;
  min_ram_gb?: number | null;
  min_storage_gb?: number | null;
  min_vram_gb?: number | null;
  min_weight_kg?: number | null;
  max_weight_kg?: number | null;
  brands?: string[];
  gpu_tags?: string[];
  excluded_brands?: string[];
  excluded_gpu_tags?: string[];
  storage_types?: string[];
  operating_systems?: string[];
}

export interface ApiParsedQuery {
  original_query: string;
  semantic_query: string;
  embedding_query?: string;
  semantic_constraints?: string[];
  filters: ApiSearchFilters;
  inferred_filters?: ApiSearchFilters;
  locked_fields?: string[];
  confidence?: number;
  warnings?: string[];
}

export interface ApiSourceChunk {
  vector_id: number;
  chunk_id: string;
  laptop_id: number;
  chunk_type?: string | null;
  score?: number | null;
  semantic_score?: number | null;
  filter_aware_score?: number | null;
  text: string;
}

/** Arbitrary laptop metadata fields sourced from the dataset (cpu_full,
 * ram_capacity_gb, gpu_tags, weight_kg, ...). Keys vary per record. */
export type ApiLaptopMetadata = Record<string, unknown>;

export interface ApiLaptopRecommendation {
  laptop_id: number;
  brand: string;
  model: string;
  price_usd?: number | null;
  score?: number | null;
  semantic_score?: number | null;
  filter_aware_score?: number | null;
  constraint_fit_score?: number | null;
  soft_preference_score?: number | null;
  value_score?: number | null;
  price_fit_score?: number | null;
  spec_score?: number | null;
  metadata: ApiLaptopMetadata;
  sources: ApiSourceChunk[];
}

export interface ApiRetrievalCandidate {
  vector_id: number;
  laptop_id?: number | null;
  score: number;
  brand?: string | null;
  model?: string | null;
  price_usd?: number | null;
}

export interface ApiCardInsight {
  match_reason: string;
  strengths: string[];
  tradeoffs: string[];
}

export interface ChatResponseDTO {
  status: string;
  message?: string | null;
  search_mode: string;
  index_used?: ApiIndexType | null;
  candidate_k?: number | null;
  matched_count: number;
  requested_top_k: number;
  candidate_hits?: ApiRetrievalCandidate[];
  parsed_query: ApiParsedQuery;
  outlier: boolean;
  recommendations: ApiLaptopRecommendation[];
  relaxed_filters: string[];
  retrieval_latency_ms: number;
  timings_ms?: Record<string, number>;
  answer: string;
  provider: string;
  cache_hit: boolean;
  conversation_id: string;
  intent: ChatIntent;
  referenced_laptop_ids: number[];
  /** JSON round-trips dict[int, CardInsight] keys as strings. */
  card_insights: Record<string, ApiCardInsight>;
}

export interface ChatRequestDTO {
  message?: string;
  conversation_id?: string;
  grounding_laptop_ids?: number[];
  filters?: ApiSearchFilters;
  top_k?: number;
  /** Set only for /suggest or an explicit filter search. Omitted/false
   * means chat grounded in the last retrieved set; without one, the backend
   * asks the user to create grounding first. */
  force_retrieval?: boolean;
  /** True unless the user turned on "Strict budget" — lets the backend
   * include slightly-over-budget laptops when an exact budget is too thin. */
  allow_filter_relaxation?: boolean;
  /** Omitted unless the user explicitly picked one from the index-type
   * dropdown — the backend falls back to its own configured default. */
  index_type?: ApiIndexType | null;
}

export interface ApiLaptopListItem extends ApiLaptopMetadata {
  laptop_id: number;
  brand: string;
  model: string;
  price_usd?: number | null;
}

export interface LaptopListResponseDTO {
  total: number;
  limit: number;
  offset: number;
  items: ApiLaptopListItem[];
  facets: {
    brands: string[];
    gpu_tags: string[];
    operating_systems: string[];
  };
}

export interface LaptopDetailResponseDTO {
  laptop_id: number;
  laptop: ApiLaptopListItem & { content_by_type?: Record<string, string[]> };
  chunks: ApiLaptopMetadata[];
}

export interface SimilarLaptopsResponseDTO {
  laptop_id: number;
  similar: (ApiLaptopListItem & { content_by_type?: Record<string, string[]>; similarity: number })[];
}

// --- POST /chat/stream (Server-Sent Events) ---
// Progressive previews only — the final "done" event's payload is a full
// ChatResponseDTO and is always the source of truth for the message.

export interface StreamRecommendationsEventDTO {
  recommendations: ApiLaptopRecommendation[];
  status: string;
  outlier: boolean;
  message: string | null;
  matched_count: number;
  intent: ChatIntent;
}

export interface StreamAnswerEventDTO {
  answer: string;
  provider: string;
}

export interface StreamCardInsightsEventDTO {
  card_insights: Record<string, ApiCardInsight>;
}

export interface StreamErrorEventDTO {
  detail: string;
}

export interface ApiIndexOption {
  id: ApiIndexType;
  label: string;
  default: boolean;
  available: boolean;
  parameters: Record<string, unknown>;
  benchmark: { recall_at_10?: number; p50_ms?: number; size_mb?: number };
}

export interface IndexSettingsResponseDTO {
  candidate_k: number;
  final_top_k: number;
  default_index: ApiIndexType;
  indexes: ApiIndexOption[];
}

export interface HealthResponseDTO {
  status: string;
  version: string;
  embedding_model: string;
  embedding_ready: boolean;
  faiss_ready: boolean;
  metadata_backend: string;
  metadata_ready: boolean;
  qdrant_ready: boolean;
  llm_providers: string[];
  errors: string[];
}
