import type { RagDebugInfo, RecommendationRequest, RecommendationResponse } from "@/types/chat";
import type {
  Laptop,
  LaptopFilters,
  LaptopRecommendation,
  MatchBreakdown,
  RequirementMatch,
  RetrievedEvidence,
} from "@/types/laptop";
import type {
  ApiCardInsight,
  ApiLaptopRecommendation,
  ApiSearchFilters,
  ChatIntent,
  ChatRequestDTO,
  ChatResponseDTO,
  StreamAnswerEventDTO,
  StreamCardInsightsEventDTO,
  StreamErrorEventDTO,
  StreamRecommendationsEventDTO,
} from "@/types/api";
import { apiFetch, API_BASE_URL, ApiError, DEFAULT_REQUEST_TIMEOUT_MS, USE_MOCK_API } from "./apiClient";
import { mockGetRecommendations } from "@/mocks/mockEngine";
import { calibrateMatchScore, formatLaptopName } from "@/lib/utils";

/** The backend has no structured filter for RAM/price/storage/brand/OS
 * beyond what's listed here — it infers use-case, CPU-brand, and display-size
 * preferences from free text instead of a dedicated filter field. Fold the
 * FilterPanel's selections for those into the outgoing message so the
 * parser/embedding still sees them rather than silently dropping intent. */
function toApiFilters(filters?: LaptopFilters): ApiSearchFilters {
  if (!filters) return {};
  return {
    min_price_usd: filters.minPrice,
    max_price_usd: filters.maxPrice,
    min_ram_gb: filters.minRam,
    min_storage_gb: filters.minStorage,
    min_vram_gb: filters.minVram,
    brands: filters.brands?.map((brand) => brand.toLowerCase()),
    operating_systems: filters.operatingSystem?.map((os) => os.toLowerCase()),
  };
}

function augmentMessage(query: string, filters?: LaptopFilters): string {
  const extras: string[] = [];
  if (filters?.useCases?.length) extras.push(`Use case: ${filters.useCases.join(", ")}.`);
  if (filters?.cpuBrand?.length && !filters.cpuBrand.includes("Any")) {
    extras.push(`Prefer ${filters.cpuBrand.join(" or ")} CPU.`);
  }
  if (filters?.displaySize?.length) extras.push(`Display size: ${filters.displaySize.join(", ")}.`);
  if (extras.length === 0) return query;
  return `${query} ${extras.join(" ")}`.trim();
}

function metadataString(metadata: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const value = metadata[key];
    if (value === null || value === undefined) continue;
    if (Array.isArray(value)) {
      if (value.length > 0) return value.join(", ");
      continue;
    }
    const text = String(value).trim();
    if (text) return text;
  }
  return undefined;
}

function toLaptop(item: ApiLaptopRecommendation): Laptop {
  const metadata = item.metadata ?? {};
  const ramGb = metadata["ram_capacity_gb"];
  const storageGb = metadata["storage_capacity_gb"];
  const weightKg = metadata["weight_kg"];
  return {
    id: String(item.laptop_id),
    name: formatLaptopName(item.brand, item.model),
    brand: item.brand,
    price: item.price_usd ?? undefined,
    cpu: metadataString(metadata, "cpu_full"),
    ram: metadataString(metadata, "ram_full") ?? (typeof ramGb === "number" ? `${ramGb} GB` : undefined),
    storage:
      metadataString(metadata, "storage") ??
      (typeof storageGb === "number" ? `${storageGb} GB` : undefined),
    gpu: metadataString(metadata, "gpu_full", "gpu_tags"),
    display: metadataString(metadata, "display_full"),
    battery: metadataString(metadata, "battery"),
    weight: typeof weightKg === "number" ? `${weightKg} kg` : metadataString(metadata, "weight_kg"),
    operatingSystem: metadataString(metadata, "os", "os_normalized"),
  };
}

function toEvidence(item: ApiLaptopRecommendation): RetrievedEvidence[] {
  return item.sources.map((source) => ({
    id: source.chunk_id,
    source: formatLaptopName(item.brand, item.model),
    sourceType: source.chunk_type === "spec" ? "spec" : "review",
    text: source.text,
    score: source.score ?? undefined,
  }));
}

function toBreakdown(item: ApiLaptopRecommendation): MatchBreakdown[] {
  const entries: [string, number | null | undefined][] = [
    ["Semantic Match", item.semantic_score],
    ["Requirement Fit", item.constraint_fit_score],
    ["Value", item.value_score],
    ["Price Fit", item.price_fit_score],
  ];
  return entries
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([label, value]) => ({ label, value: Math.round((value as number) * 100) }));
}

/** Mirrors the shape of `RetrievalService._constraint_fit` on the backend,
 * but per-field and human-readable instead of a single aggregate score. */
function deriveRequirementMatches(
  filters: ApiSearchFilters,
  metadata: Record<string, unknown>
): RequirementMatch[] {
  const matches: RequirementMatch[] = [];
  const num = (value: unknown) => (typeof value === "number" ? value : undefined);

  if (filters.max_price_usd != null) {
    const price = num(metadata["price_usd"]);
    matches.push({
      label: `Budget ≤ $${filters.max_price_usd.toLocaleString()}`,
      status: price !== undefined && price <= filters.max_price_usd ? "met" : "unmet",
      detail: price !== undefined ? `$${price.toLocaleString()}` : undefined,
    });
  }
  if (filters.min_ram_gb != null) {
    const ram = num(metadata["ram_capacity_gb"]);
    matches.push({
      label: `RAM ≥ ${filters.min_ram_gb} GB`,
      status: ram !== undefined && ram >= filters.min_ram_gb ? "met" : ram !== undefined ? "partial" : "unmet",
      detail: ram !== undefined ? `${ram} GB` : undefined,
    });
  }
  if (filters.min_storage_gb != null) {
    const storage = num(metadata["storage_capacity_gb"]);
    matches.push({
      label: `Storage ≥ ${filters.min_storage_gb} GB`,
      status: storage !== undefined && storage >= filters.min_storage_gb ? "met" : "partial",
      detail: storage !== undefined ? `${storage} GB` : undefined,
    });
  }
  if (filters.min_vram_gb != null) {
    const vram = num(metadata["vram_capacity_gb"]);
    matches.push({
      label: `VRAM ≥ ${filters.min_vram_gb} GB`,
      status: vram !== undefined && vram >= filters.min_vram_gb ? "met" : "unmet",
      detail: vram !== undefined ? `${vram} GB` : undefined,
    });
  }
  if (filters.brands?.length) {
    const brand = String(metadata["brand_normalized"] ?? "").toLowerCase();
    matches.push({
      label: `Brand: ${filters.brands.join(", ")}`,
      status: filters.brands.includes(brand) ? "met" : "unmet",
    });
  }
  return matches;
}

function toRecommendations(
  items: ApiLaptopRecommendation[],
  filters: ApiSearchFilters,
  cardInsights?: Record<string, ApiCardInsight>
): LaptopRecommendation[] {
  let bestValueId: number | null = null;
  let bestValueScore = -Infinity;
  for (const item of items) {
    if (item.value_score != null && item.value_score > bestValueScore) {
      bestValueScore = item.value_score;
      bestValueId = item.laptop_id;
    }
  }

  return items.map((item, index) => {
    const insight = cardInsights?.[String(item.laptop_id)];
    const tier: LaptopRecommendation["tier"] =
      index === 0 ? "best-match" : item.laptop_id === bestValueId ? "best-value" : "alternative";
    return {
      laptop: toLaptop(item),
      // MatchScore multiplies by 100 itself — keep this as a 0-1 fraction.
      matchScore: item.score != null ? calibrateMatchScore(item.score) : undefined,
      matchBreakdown: toBreakdown(item),
      reasoning:
        insight?.match_reason ?? "Matches your stated requirements based on retrieved specifications.",
      matchedRequirements: deriveRequirementMatches(filters, item.metadata ?? {}),
      evidence: toEvidence(item),
      tier,
      strengths: insight?.strengths,
      tradeoffs: insight?.tradeoffs,
    };
  });
}

function hasExactMatches(status: string, outlier: boolean): boolean {
  return !outlier && status !== "no_metadata_match" && status !== "no_relevant_match";
}

let cachedEmbeddingModel: string | undefined | null = null;

/** Cached for the session — the embedding model never changes at runtime. */
async function getEmbeddingModel(): Promise<string | undefined> {
  if (cachedEmbeddingModel !== null) return cachedEmbeddingModel;
  try {
    const health = await apiFetch<{ embedding_model: string }>("/health");
    cachedEmbeddingModel = health.embedding_model;
  } catch {
    cachedEmbeddingModel = undefined;
  }
  return cachedEmbeddingModel;
}

function toDebug(
  dto: ChatResponseDTO,
  query: string,
  filters: LaptopFilters | undefined,
  embeddingModel: string | undefined
): RagDebugInfo {
  return {
    query,
    filters,
    embeddingModel,
    faissIndexType: dto.index_used ?? undefined,
    topK: dto.requested_top_k,
    retrievedIds: dto.recommendations.map((item) => String(item.laptop_id)),
    retrievalLatencyMs: dto.retrieval_latency_ms,
    totalLatencyMs: dto.retrieval_latency_ms,
  };
}

async function adaptChatResponse(
  dto: ChatResponseDTO,
  query: string,
  filters?: LaptopFilters
): Promise<RecommendationResponse> {
  const embeddingModel = await getEmbeddingModel();
  return {
    answer: dto.answer,
    recommendations: toRecommendations(dto.recommendations, dto.parsed_query?.filters ?? {}, dto.card_insights),
    retrievedContext: dto.recommendations.flatMap(toEvidence),
    hasExactMatches: hasExactMatches(dto.status, dto.outlier),
    message: dto.message,
    relaxedFilters: dto.relaxed_filters,
    debug: toDebug(dto, query, filters, embeddingModel),
    conversationId: dto.conversation_id,
    intent: dto.intent,
    referencedLaptopIds: dto.referenced_laptop_ids?.map(String),
  };
}

function buildChatRequestBody(request: RecommendationRequest): ChatRequestDTO {
  return {
    message: augmentMessage(request.query, request.filters),
    conversation_id: request.conversationId,
    grounding_laptop_ids: request.groundingLaptopIds?.map(Number).filter(Number.isSafeInteger),
    filters: toApiFilters(request.filters),
    top_k: request.top_k,
    force_retrieval: request.forceRetrieval ?? false,
    allow_filter_relaxation: !request.filters?.strictBudget,
    index_type: request.indexType,
  };
}

export interface StreamCallbacks {
  /** Fires the moment retrieval finishes — well before the LLM responds —
   * so cards can render immediately instead of waiting for the full answer. */
  onRecommendations?: (preview: {
    recommendations: LaptopRecommendation[];
    hasExactMatches: boolean;
    intent: ChatIntent;
  }) => void;
  onAnswer?: (answer: string) => void;
  /** Recommendations re-derived with real "why it matches" text merged in
   * (they render with generic placeholder reasoning until this arrives). */
  onCardInsights?: (recommendations: LaptopRecommendation[]) => void;
  /** Always fires last, with the complete, authoritative response — exactly
   * what getRecommendations() would have resolved with non-streaming. */
  onDone: (response: RecommendationResponse) => void;
}

/** Parses one "event: X\ndata: Y" SSE message block. Our backend always
 * emits single-line JSON payloads, so no multi-line `data:` handling is
 * needed here. */
function parseSseMessage(block: string): { event: string; data: unknown } | null {
  const eventLine = block.split("\n").find((line) => line.startsWith("event:"));
  const dataLine = block.split("\n").find((line) => line.startsWith("data:"));
  if (!eventLine || !dataLine) return null;
  try {
    return {
      event: eventLine.slice("event:".length).trim(),
      data: JSON.parse(dataLine.slice("data:".length).trim()),
    };
  } catch {
    return null;
  }
}

/** Streaming counterpart to getRecommendations(): recommendation cards
 * appear as soon as retrieval completes (~100-200ms) instead of waiting for
 * the full LLM round trip (often 3-5s). Falls back to a single onDone call
 * in mock mode, where there's nothing to stream. */
export async function streamRecommendations(
  request: RecommendationRequest,
  callbacks: StreamCallbacks
): Promise<void> {
  if (USE_MOCK_API) {
    callbacks.onDone(await mockGetRecommendations(request));
    return;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DEFAULT_REQUEST_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildChatRequestBody(request)),
      signal: controller.signal,
    });
  } catch (error) {
    clearTimeout(timeout);
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(`Request to /chat/stream timed out after ${DEFAULT_REQUEST_TIMEOUT_MS / 1000}s.`);
    }
    throw error;
  }
  if (!response.ok || !response.body) {
    clearTimeout(timeout);
    throw new ApiError(`Request to /chat/stream failed with status ${response.status}`, response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let latestRecommendations: ApiLaptopRecommendation[] = [];
  let doneReceived = false;
  const filters = toApiFilters(request.filters);

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        const message = parseSseMessage(block);
        if (!message) continue;

        if (message.event === "recommendations") {
          const data = message.data as StreamRecommendationsEventDTO;
          latestRecommendations = data.recommendations;
          callbacks.onRecommendations?.({
            recommendations: toRecommendations(data.recommendations, filters),
            hasExactMatches: hasExactMatches(data.status, data.outlier),
            intent: data.intent,
          });
        } else if (message.event === "answer") {
          const data = message.data as StreamAnswerEventDTO;
          callbacks.onAnswer?.(data.answer);
        } else if (message.event === "card_insights") {
          const data = message.data as StreamCardInsightsEventDTO;
          callbacks.onCardInsights?.(toRecommendations(latestRecommendations, filters, data.card_insights));
        } else if (message.event === "done") {
          const dto = message.data as ChatResponseDTO;
          doneReceived = true;
          callbacks.onDone(await adaptChatResponse(dto, request.query, request.filters));
        } else if (message.event === "error") {
          const data = message.data as StreamErrorEventDTO;
          throw new ApiError(data.detail || "The stream ended unexpectedly.");
        }
      }
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(`Stream to /chat/stream timed out after ${DEFAULT_REQUEST_TIMEOUT_MS / 1000}s.`);
    }
    throw error;
  } finally {
    clearTimeout(timeout);
    // Explicitly release the connection instead of letting it dangle — an
    // uncancelled reader on a broken stream can pile up against the
    // browser's per-origin connection limit and stall unrelated requests.
    reader.cancel().catch(() => {});
  }

  // The connection closed (server restarted, proxy dropped it, etc.)
  // without ever sending "done" or "error" — surface that as a failure
  // instead of resolving silently, which would otherwise leave the message
  // stuck mid-stream and the input permanently disabled (nothing else ever
  // clears the "still sending" state).
  if (!doneReceived) {
    throw new ApiError("The connection closed before a response was received.");
  }
}
