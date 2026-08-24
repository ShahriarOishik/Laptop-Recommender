import { useEffect, useState } from "react";
import type { LaptopFilters } from "@/types/laptop";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { FilterPanel } from "@/components/filters/FilterPanel";
import { cn } from "@/lib/utils";

export function HomePage() {
  const [filters, setFilters] = useState<LaptopFilters>({});
  const [filtersOpen, setFiltersOpen] = useState(false);

  useEffect(() => {
    if (!filtersOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFiltersOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [filtersOpen]);

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
        <ChatWindow
          filters={filters}
          onToggleFilters={() => setFiltersOpen((v) => !v)}
          onClearFilters={() => setFilters({})}
        />
      </div>

      <div
        role="region"
        aria-labelledby="filter-panel-heading"
        aria-hidden={!filtersOpen}
        className={cn(
          "hidden flex-shrink-0 overflow-hidden border-l border-[var(--color-border)] bg-[var(--color-surface)] transition-all duration-200 motion-reduce:transition-none lg:block",
          filtersOpen ? "w-80" : "w-0"
        )}
      >
        <div className="h-full w-80">
          <FilterPanel filters={filters} onChange={setFilters} />
        </div>
      </div>

      {filtersOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setFiltersOpen(false)}
            aria-hidden="true"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="filter-panel-heading"
            className="absolute right-0 top-0 h-full w-80 max-w-[85vw] bg-[var(--color-surface)] shadow-2xl"
          >
            <FilterPanel filters={filters} onChange={setFilters} onClose={() => setFiltersOpen(false)} />
          </div>
        </div>
      )}
    </div>
  );
}
