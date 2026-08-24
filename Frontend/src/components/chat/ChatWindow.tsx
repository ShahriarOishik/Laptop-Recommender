import { useLayoutEffect, useRef } from "react";
import { Sparkles, SlidersHorizontal, X } from "lucide-react";
import { useChatHistory } from "@/context/ChatHistoryContext";
import type { LaptopFilters } from "@/types/laptop";
import type { Laptop } from "@/types/laptop";
import { generateId, summarizeRequirements } from "@/lib/utils";
import { streamRecommendations } from "@/services/recommendationService";
import { ChatMessage } from "./ChatMessage";
import { ChatInput, type SubmitOptions } from "./ChatInput";
import { SuggestedPrompts } from "./SuggestedPrompts";
import { countActiveFilters } from "@/components/filters/FilterPanel";
import { Button } from "@/components/common/Button";
import { useDeveloperMode } from "@/context/DeveloperModeContext";
import type { ApiIndexType } from "@/types/api";

interface SendOptions {
  filtersOverride?: LaptopFilters;
  forceRetrieval?: boolean;
  indexType?: ApiIndexType;
  topK?: number;
}

export function ChatWindow({
  filters,
  onToggleFilters,
  onClearFilters,
}: {
  filters: LaptopFilters;
  onToggleFilters: () => void;
  onClearFilters?: () => void;
}) {
  const {
    activeSession,
    addMessage,
    updateMessage,
    setSessionConversationId,
    pendingSessionIds,
    markSessionSending,
    clearSessionSending,
  } = useChatHistory();
  const { indexType, topK } = useDeveloperMode();
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const latestUserMessageRef = useRef<HTMLDivElement>(null);
  const messages = activeSession.messages;
  const activeFilterCount = countActiveFilters(filters);
  // Scoped to *this* session specifically (not one flag shared across the
  // whole app) — otherwise switching to a different chat while a response
  // is still streaming would leave that other chat's input locked for a
  // request it never made. Distinct from a message's `isLoading` (which
  // only gates the initial full-skeleton vs. partial-content display):
  // this stays true for the entire streamed turn, including while
  // recommendations are already visible but the answer/card insights are
  // still arriving.
  const isSending = pendingSessionIds.has(activeSession.id);

  const latestUserMessageId = [...messages].reverse().find((message) => message.role === "user")?.id;
  const latestSuggestion = [...messages].reverse().find(
    (message) =>
      message.role === "assistant" &&
      !!message.recommendations?.length &&
      (message.intent === undefined ||
        message.intent === "new_recommendation" ||
        message.intent === "updated_requirements")
  );
  const latestSuggestionId = latestSuggestion?.id;

  useLayoutEffect(() => {
    const container = scrollContainerRef.current;
    const userMessage = latestUserMessageRef.current;
    if (!container || !userMessage) return;
    container.scrollTo({ top: Math.max(0, userMessage.offsetTop - 16), behavior: "auto" });
  }, [activeSession.id, latestUserMessageId]);

  const handleSend = async (query: string, options?: SendOptions) => {
    const sessionId = activeSession.id;
    const forceRetrieval = options?.forceRetrieval ?? false;
    const effectiveFilters = forceRetrieval ? options?.filtersOverride ?? filters : undefined;
    const requestIndexType = options?.indexType ?? indexType;
    const requestTopK = options?.topK ?? topK;
    // A /suggest with no text and only filters set is valid (it runs a pure
    // filter search) — the empty string still goes to the API as-is so the
    // backend takes the metadata-only path, this is purely a transcript label.
    const displayText = query || (forceRetrieval ? "Search using current filters" : query);

    addMessage(sessionId, {
      id: generateId("msg"),
      role: "user",
      text: displayText,
      isCommand: forceRetrieval,
      createdAt: Date.now(),
    });

    const assistantId = generateId("msg");
    addMessage(sessionId, {
      id: assistantId,
      role: "assistant",
      isLoading: true,
      createdAt: Date.now(),
    });
    markSessionSending(sessionId);

    try {
      await streamRecommendations(
        {
          query,
          filters: effectiveFilters,
          top_k: forceRetrieval ? requestTopK : undefined,
          indexType: forceRetrieval ? requestIndexType : undefined,
          groundingLaptopIds: forceRetrieval
            ? undefined
            : latestSuggestion?.recommendations?.map((item) => item.laptop.id),
          conversationId: activeSession.conversationId,
          forceRetrieval,
        },
        {
          onRecommendations: ({ recommendations, hasExactMatches, intent }) => {
            updateMessage(sessionId, assistantId, {
              isLoading: false,
              isAnswerPending: true,
              recommendations,
              hasExactMatches,
              intent,
              requestQuery: query,
              requestFilters: effectiveFilters,
              requestForceRetrieval: forceRetrieval,
              requestIndexType: requestIndexType,
              requestTopK: requestTopK,
            });
          },
          onAnswer: (answer) => {
            updateMessage(sessionId, assistantId, { isLoading: false, isAnswerPending: false, text: answer });
          },
          onCardInsights: (recommendations) => {
            updateMessage(sessionId, assistantId, { recommendations });
          },
          onDone: (response) => {
            if (response.conversationId && response.conversationId !== activeSession.conversationId) {
              setSessionConversationId(sessionId, response.conversationId);
            }
            updateMessage(sessionId, assistantId, {
              isLoading: false,
              isAnswerPending: false,
              text: response.answer,
              recommendations: response.recommendations,
              retrievedContext: response.retrievedContext,
              hasExactMatches: response.hasExactMatches,
              message: response.message,
              relaxedFilters: response.relaxedFilters,
              requestQuery: query,
              requestFilters: effectiveFilters,
              requestForceRetrieval: forceRetrieval,
              requestIndexType: requestIndexType,
              requestTopK: requestTopK,
              debug: response.debug,
              intent: response.intent,
              referencedLaptopIds: response.referencedLaptopIds,
            });
            clearSessionSending(sessionId);
          },
        }
      );
    } catch {
      updateMessage(sessionId, assistantId, {
        isLoading: false,
        isAnswerPending: false,
        isError: true,
        requestQuery: query,
        requestFilters: effectiveFilters,
        requestForceRetrieval: forceRetrieval,
        requestIndexType: requestIndexType,
        requestTopK: requestTopK,
      });
      clearSessionSending(sessionId);
    }
  };

  const handleSubmit = (value: string, options: SubmitOptions) => {
    handleSend(value, { forceRetrieval: options.forceRetrieval });
  };

  const handleAskAI = (laptop: Laptop) => {
    handleSend(`Tell me more about the ${laptop.name} — is it a good fit for my needs?`);
  };

  const activeFilterSummary = activeFilterCount > 0 ? summarizeRequirements("", filters) : [];

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-3xl flex-col overflow-hidden px-3 sm:px-4">
      <div ref={scrollContainerRef} className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">
        {messages.length === 0 ? (
          <div className="flex min-h-full flex-col items-center justify-center gap-8 py-10">
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--color-accent)] text-white">
                <Sparkles className="h-6 w-6" aria-hidden="true" />
              </div>
              <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-text)]">
                Find the Right Laptop with AI
              </h1>
              <p className="mx-auto mt-2 max-w-md text-sm text-[var(--color-text-muted)]">
                Run <code className="rounded bg-[var(--color-surface-2)] px-1.5 py-0.5 font-mono text-[13px]">/suggest</code>{" "}
                with your budget, use case, and specs to get ranked recommendations. Plain
                messages are just chat — ask follow-ups, comparisons, or general questions any
                time.
              </p>
            </div>
            <div className="w-full max-w-xl">
              <SuggestedPrompts onSelect={(prompt) => handleSend(prompt, { forceRetrieval: true })} />
            </div>
          </div>
        ) : (
          <div className="space-y-6 py-6">
            {messages.map((message) => (
              <div
                key={message.id}
                ref={message.id === latestUserMessageId ? latestUserMessageRef : undefined}
              >
                <ChatMessage
                  message={message}
                  onRetry={() =>
                    message.requestQuery !== undefined &&
                    handleSend(message.requestQuery, {
                      filtersOverride: message.requestFilters,
                      forceRetrieval: message.requestForceRetrieval,
                      indexType: message.requestIndexType,
                      topK: message.requestTopK,
                    })
                  }
                  onFollowUp={message.id === latestSuggestionId ? (question) => handleSend(question) : undefined}
                  onAskAI={handleAskAI}
                  actionsDisabled={isSending || message.id !== latestSuggestionId}
                  onModifyFilters={onToggleFilters}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex-shrink-0 pb-3 pt-2 sm:pb-4">
        {activeFilterSummary.length > 0 && (
          <div
            className="mb-2 flex flex-wrap items-center gap-1.5 rounded-xl border border-[var(--color-accent)]/25 bg-[var(--color-accent-soft)] px-3 py-2 text-xs"
            role="status"
            aria-label="Active search filters that will apply to your next /suggest search"
          >
            <SlidersHorizontal className="h-3.5 w-3.5 flex-shrink-0 text-[var(--color-accent)]" aria-hidden="true" />
            <span className="font-medium text-[var(--color-accent)]">Filters ready:</span>
            {activeFilterSummary.map((line) => (
              <span
                key={line}
                className="rounded-full bg-[var(--color-surface)] px-2 py-0.5 text-[var(--color-text-muted)]"
              >
                {line}
              </span>
            ))}
            {onClearFilters && (
              <button
                type="button"
                onClick={onClearFilters}
                aria-label="Clear all active filters"
                className="ml-auto flex items-center gap-1 rounded-full px-2 py-0.5 text-[var(--color-accent)] hover:bg-[var(--color-surface)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              >
                <X className="h-3 w-3" aria-hidden="true" />
                Clear
              </button>
            )}
            <Button
              size="sm"
              variant="primary"
              className="ml-auto"
              disabled={isSending}
              onClick={() => handleSend("", { forceRetrieval: true })}
            >
              Apply Filters
            </Button>
          </div>
        )}
        <ChatInput
          onSubmit={handleSubmit}
          disabled={isSending}
          activeFilterCount={activeFilterCount}
          onToggleFilters={onToggleFilters}
        />
        <p className="mt-2 text-center text-[11px] text-[var(--color-text-faint)]">
          <code className="font-mono">/suggest a gaming laptop under $1,200 with 16GB RAM</code> to
          search · anything else is chat about your results
        </p>
      </div>
    </div>
  );
}
