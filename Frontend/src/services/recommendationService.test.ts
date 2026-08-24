import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./apiClient";
import { streamRecommendations } from "./recommendationService";

/** Builds a fetch Response whose body streams the given SSE text, then
 * closes the connection — simulating both a normal stream and a server
 * that dies mid-request without ever sending "done"/"error". */
function sseResponse(text: string): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(text));
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
}

describe("streamRecommendations", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("throws instead of resolving silently when the stream closes without a done event", async () => {
    // Simulates the server process dying mid-request (e.g. a restart) —
    // the connection just ends with no "done"/"error" SSE message.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        sseResponse(
          'event: recommendations\ndata: {"recommendations":[],"status":"ok","outlier":false,"message":null,"matched_count":0,"intent":"new_recommendation"}\n\n'
        )
      )
    );

    const onDone = vi.fn();
    let caught: unknown;
    try {
      await streamRecommendations({ query: "gaming laptop", forceRetrieval: true }, { onDone });
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).message).toMatch(/connection closed/i);
    expect(onDone).not.toHaveBeenCalled();
  });

  it("resolves normally and calls onDone when a done event arrives", async () => {
    const doneEvent = {
      status: "ok",
      search_mode: "hybrid",
      matched_count: 0,
      requested_top_k: 5,
      parsed_query: { original_query: "x", semantic_query: "x", filters: {} },
      outlier: false,
      recommendations: Array.from({ length: 5 }, (_, index) => ({
        laptop_id: 100 + index,
        brand: "Test",
        model: `Laptop ${index + 1}`,
        metadata: {},
        sources: [],
      })),
      candidate_hits: Array.from({ length: 20 }, (_, index) => ({
        vector_id: index,
        laptop_id: 100 + index,
        score: 1 - index / 100,
      })),
      retrieval_latency_ms: 1,
      answer: "Here you go.",
      provider: "groq",
      cache_hit: false,
      conversation_id: "abc",
      intent: "new_recommendation",
      referenced_laptop_ids: [],
      card_insights: {},
    };
    // Both /chat/stream and the embedding-model /health lookup inside
    // adaptChatResponse go through this same stub; /health gets the same
    // body and fails to parse as its expected shape, which
    // getEmbeddingModel() already tolerates (catches, returns undefined).
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        Promise.resolve(sseResponse(`event: done\ndata: ${JSON.stringify(doneEvent)}\n\n`))
      )
    );

    const onDone = vi.fn();
    await streamRecommendations({ query: "gaming laptop", forceRetrieval: true }, { onDone });
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(onDone.mock.calls[0][0].answer).toBe("Here you go.");
    expect(onDone.mock.calls[0][0].debug.retrievedIds).toEqual(["100", "101", "102", "103", "104"]);
  });
});
