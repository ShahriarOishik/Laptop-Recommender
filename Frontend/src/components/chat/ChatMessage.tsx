import { Link } from "react-router-dom";
import { Search, SearchX, Sparkles, User } from "lucide-react";
import type { ChatMessage as ChatMessageType } from "@/types/chat";
import type { Laptop } from "@/types/laptop";
import { formatPrice, summarizeRequirements } from "@/lib/utils";
import { LaptopRecommendationCard } from "@/components/laptop/LaptopRecommendationCard";
import { ChatLoadingState } from "./ChatLoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { FollowUpSuggestions } from "./FollowUpSuggestions";
import { Button } from "@/components/common/Button";

export function ChatMessage({
  message,
  onRetry,
  onFollowUp,
  onAskAI,
  actionsDisabled,
  onModifyFilters,
}: {
  message: ChatMessageType;
  onRetry?: () => void;
  onFollowUp?: (question: string) => void;
  onAskAI?: (laptop: Laptop) => void;
  actionsDisabled?: boolean;
  onModifyFilters?: () => void;
}) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end gap-2 sm:gap-2.5">
        <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-[var(--color-accent)] px-4 py-2.5 text-sm text-white sm:max-w-lg">
          {message.isCommand && (
            <span className="mb-1 flex items-center gap-1 font-mono text-[10px] font-semibold uppercase tracking-wide text-white/70">
              <Search className="h-3 w-3" aria-hidden="true" />
              /suggest search
            </span>
          )}
          {message.text}
        </div>
        <div
          className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-[var(--color-surface-2)] text-[var(--color-text-muted)]"
          aria-hidden="true"
        >
          <User className="h-3.5 w-3.5" />
        </div>
      </div>
    );
  }

  // Full recommendation cards are for actual suggestions (a new or updated
  // recommendation set). Follow-up/general answers are conversational —
  // they get the text answer plus a compact reference to whichever laptops
  // are being discussed, not a repeated card grid.
  const isSuggestion =
    message.intent === undefined ||
    message.intent === "new_recommendation" ||
    message.intent === "updated_requirements";
  const hasRecommendations = !!message.recommendations && message.recommendations.length > 0;
  const recommendationCards = hasRecommendations ? (
    <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
      {message.recommendations!.map((rec) => (
        <LaptopRecommendationCard
          key={rec.laptop.id}
          recommendation={rec}
          onAskAI={onAskAI}
          actionsDisabled={actionsDisabled}
        />
      ))}
    </div>
  ) : null;

  if (message.requestForceRetrieval && !message.isLoading && !message.isError) {
    return (
      <div className="min-w-0 flex-1" aria-live="polite">
        {recommendationCards}
      </div>
    );
  }

  return (
    <div className="flex gap-2.5">
      <div
        className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-[var(--color-accent)] text-white"
        aria-hidden="true"
      >
        <Sparkles className="h-3.5 w-3.5" />
      </div>
      <div
        className="min-w-0 flex-1 space-y-4"
        aria-live="polite"
        aria-busy={message.isLoading || message.isAnswerPending || undefined}
      >
        {message.isLoading && <ChatLoadingState />}

        {message.isError && <ErrorState onRetry={onRetry} />}

        {!message.isLoading && !message.isError && (
          <>
            {message.text && (
              <p className="max-w-2xl rounded-2xl rounded-tl-sm bg-[var(--color-surface-2)] px-4 py-2.5 text-sm text-[var(--color-text)]">
                {message.text}
              </p>
            )}

            {!message.text && message.isAnswerPending && (
              <div className="flex items-center gap-2 text-xs text-[var(--color-text-faint)]">
                <span className="flex gap-0.5" aria-hidden="true">
                  <span className="h-1 w-1 animate-bounce rounded-full bg-current [animation-delay:-0.3s]" />
                  <span className="h-1 w-1 animate-bounce rounded-full bg-current [animation-delay:-0.15s]" />
                  <span className="h-1 w-1 animate-bounce rounded-full bg-current" />
                </span>
                Writing an explanation…
              </div>
            )}

            {!!message.relaxedFilters?.length && message.message && (
              <div className="flex items-start gap-3 rounded-2xl border border-dashed border-[var(--color-border)] px-4 py-3">
                <SearchX className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--color-text-faint)]" />
                <p className="text-xs text-[var(--color-text-muted)]">{message.message}</p>
              </div>
            )}

            {message.hasExactMatches === false && (
              <div className="flex items-start gap-3 rounded-2xl border border-dashed border-[var(--color-border)] px-4 py-4">
                <SearchX className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--color-text-faint)]" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-[var(--color-text)]">No exact matches found</p>
                  <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
                    We couldn't find a laptop in the current dataset that satisfies all your
                    requirements. Showing the closest matches below.
                  </p>
                  <ul className="mt-2 space-y-0.5 text-xs text-[var(--color-text-muted)]">
                    {summarizeRequirements(message.requestQuery ?? "", message.requestFilters).map(
                      (line) => (
                        <li key={line}>• {line}</li>
                      )
                    )}
                  </ul>
                </div>
              </div>
            )}

            {isSuggestion && recommendationCards}

            {!isSuggestion && hasRecommendations && (
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <span className="font-medium text-[var(--color-text-faint)]">Referencing:</span>
                {message.recommendations!.map((rec) => (
                  <Link
                    key={rec.laptop.id}
                    to={`/laptop/${rec.laptop.id}`}
                    className="rounded-full border border-[var(--color-border)] px-2.5 py-1 text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text)]"
                  >
                    {rec.laptop.name} · {formatPrice(rec.laptop.price)}
                  </Link>
                ))}
              </div>
            )}

            {isSuggestion && hasRecommendations && onFollowUp && (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-[var(--color-text-faint)]">Follow-up questions</p>
                <FollowUpSuggestions onSelect={onFollowUp} disabled={actionsDisabled} />
              </div>
            )}

            {isSuggestion && message.recommendations && message.recommendations.length === 0 && (
              <div className="flex items-center gap-3">
                <p className="text-sm text-[var(--color-text-muted)]">
                  No laptops in the dataset are close to this request.
                </p>
                {onModifyFilters && (
                  <Button size="sm" variant="secondary" onClick={onModifyFilters}>
                    Modify Filters
                  </Button>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
