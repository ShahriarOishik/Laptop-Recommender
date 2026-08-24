import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, GitCompare, MessageCircleQuestion, Plus, RefreshCw, X } from "lucide-react";
import type { Laptop } from "@/types/laptop";
import { MAX_COMPARE, useCompare } from "@/context/CompareContext";
import { useChatHistory } from "@/context/ChatHistoryContext";
import { ComparisonTable } from "@/components/compare/ComparisonTable";
import { CatalogPicker } from "@/components/compare/CatalogPicker";
import { Button } from "@/components/common/Button";
import { formatPrice, generateId } from "@/lib/utils";

export function ComparePage() {
  const {
    compareList,
    addToCompare,
    removeFromCompare,
    replaceInCompare,
    swapCompare,
    clearCompare,
  } = useCompare();
  const { activeSession, addMessage } = useChatHistory();
  const navigate = useNavigate();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [replacingIndex, setReplacingIndex] = useState<number | null>(null);

  const openPicker = (index: number | null) => {
    setReplacingIndex(index);
    setPickerOpen(true);
  };

  const handleSelect = (laptop: Laptop) => {
    if (replacingIndex === null) addToCompare(laptop);
    else replaceInCompare(replacingIndex, laptop);
    setPickerOpen(false);
  };

  const handleAskAI = () => {
    const names = compareList.map((l) => l.name).join(", ");
    addMessage(activeSession.id, {
      id: generateId("msg"),
      role: "user",
      text: `Compare these laptops for me: ${names}`,
      createdAt: Date.now(),
    });
    navigate("/");
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-[var(--color-text)]">Compare Laptops</h1>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            {compareList.length} of {MAX_COMPARE} selected. Add, replace, or reorder laptops before comparing.
          </p>
        </div>
        {compareList.length > 0 && (
          <Button variant="ghost" size="sm" onClick={clearCompare}>
            Clear all
          </Button>
        )}
      </div>

      <section aria-labelledby="comparison-selection-heading">
        <h2 id="comparison-selection-heading" className="sr-only">Selected laptops</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {compareList.map((laptop, index) => (
            <article
              key={laptop.id}
              className="flex min-h-44 flex-col rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 shadow-sm"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-faint)]">
                    Position {index + 1}
                  </p>
                  <h3 className="mt-1 text-sm font-semibold text-[var(--color-text)]">{laptop.name}</h3>
                  <p className="text-xs text-[var(--color-text-muted)]">{laptop.brand}</p>
                </div>
                <p className="shrink-0 text-sm font-semibold text-[var(--color-text)]">{formatPrice(laptop.price)}</p>
              </div>
              <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-4">
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={index === 0}
                  onClick={() => swapCompare(index, index - 1)}
                  aria-label={`Move ${laptop.name} to position ${index}`}
                  title="Move earlier"
                  icon={<ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />}
                />
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={index === compareList.length - 1}
                  onClick={() => swapCompare(index, index + 1)}
                  aria-label={`Move ${laptop.name} to position ${index + 2}`}
                  title="Move later"
                  icon={<ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />}
                />
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => openPicker(index)}
                  aria-label={`Replace ${laptop.name}`}
                  icon={<RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />}
                >
                  Replace
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => removeFromCompare(laptop.id)}
                  aria-label={`Remove ${laptop.name} from comparison`}
                  title="Remove"
                  icon={<X className="h-3.5 w-3.5" aria-hidden="true" />}
                />
              </div>
            </article>
          ))}

          {compareList.length < MAX_COMPARE && (
            <button
              type="button"
              onClick={() => openPicker(null)}
              className="flex min-h-44 flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface-2)]/40 p-5 text-center text-[var(--color-text-muted)] transition-colors hover:border-[var(--color-accent)] hover:bg-[var(--color-accent-soft)] hover:text-[var(--color-accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              <span className="rounded-full bg-[var(--color-surface)] p-2.5 shadow-sm">
                <Plus className="h-5 w-5" aria-hidden="true" />
              </span>
              <span className="mt-2 text-sm font-semibold">Add laptop</span>
              <span className="mt-1 text-xs">Search the full catalog</span>
            </button>
          )}
        </div>
      </section>

      {compareList.length < 2 ? (
        <div className="mt-6 flex items-center gap-3 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4 text-sm text-[var(--color-text-muted)]">
          <GitCompare className="h-5 w-5 shrink-0 text-[var(--color-accent)]" aria-hidden="true" />
          {compareList.length === 0
            ? "Add at least two laptops to see a side-by-side specification table."
            : "Add one more laptop to start the side-by-side comparison."}
        </div>
      ) : (
        <div className="mt-6 space-y-4">
          <ComparisonTable laptops={compareList} onRemove={removeFromCompare} />
          <Button
            variant="primary"
            icon={<MessageCircleQuestion className="h-4 w-4" />}
            onClick={handleAskAI}
          >
            Ask AI to Compare
          </Button>
        </div>
      )}

      <CatalogPicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        selectedIds={new Set(compareList.map((laptop) => laptop.id))}
        replacingIndex={replacingIndex}
        onSelect={handleSelect}
      />
    </div>
  );
}
