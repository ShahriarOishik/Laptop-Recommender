import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Search, SlidersHorizontal } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import type { LaptopFilters } from "@/types/laptop";
import { EXPLORE_PAGE_SIZE, listLaptops, type SortOption } from "@/services/laptopService";
import { LaptopCard } from "@/components/laptop/LaptopCard";
import { FilterPanel, countActiveFilters } from "@/components/filters/FilterPanel";
import { EmptyState } from "@/components/common/EmptyState";
import { Skeleton } from "@/components/common/Skeleton";
import { cn } from "@/lib/utils";
import { visiblePageNumbers } from "./explorePagination";

const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: "name", label: "Name" },
  { value: "price-asc", label: "Price: Low to High" },
  { value: "price-desc", label: "Price: High to Low" },
];

const SORT_VALUES = new Set<SortOption>(SORT_OPTIONS.map((option) => option.value));

export function ExplorePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlSearch = searchParams.get("search") ?? "";
  const requestedSort = searchParams.get("sort") as SortOption | null;
  const sort = requestedSort && SORT_VALUES.has(requestedSort) ? requestedSort : "name";
  const requestedPage = Number(searchParams.get("page"));
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const [searchInput, setSearchInput] = useState(urlSearch);
  const [filters, setFilters] = useState<LaptopFilters>({});
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [pageInput, setPageInput] = useState(String(page));
  const activeFilterCount = countActiveFilters(filters);

  useEffect(() => {
    setSearchInput(urlSearch);
  }, [urlSearch]);

  useEffect(() => {
    if (searchInput === urlSearch) return;
    const timeout = window.setTimeout(() => {
      setSearchParams((current) => {
        const next = new URLSearchParams(current);
        const value = searchInput.trim();
        if (value) next.set("search", value);
        else next.delete("search");
        next.delete("page");
        return next;
      }, { replace: true });
    }, 300);
    return () => window.clearTimeout(timeout);
  }, [searchInput, setSearchParams, urlSearch]);

  useEffect(() => {
    setPageInput(String(page));
  }, [page]);

  const { data, error, isError, isLoading, isPlaceholderData, refetch } = useQuery({
    queryKey: ["laptops", urlSearch, sort, filters, page],
    queryFn: () => listLaptops({ search: urlSearch, sort, filters, page }),
    placeholderData: (previous) => previous,
  });

  const laptops = data?.items;
  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / EXPLORE_PAGE_SIZE));
  const rangeStart = total === 0 ? 0 : (page - 1) * EXPLORE_PAGE_SIZE + 1;
  const rangeEnd = Math.min(page * EXPLORE_PAGE_SIZE, total);

  useEffect(() => {
    if (data && !isPlaceholderData && page > pageCount) {
      setSearchParams((current) => {
        const next = new URLSearchParams(current);
        if (pageCount === 1) next.delete("page");
        else next.set("page", String(pageCount));
        return next;
      }, { replace: true });
    }
  }, [data, isPlaceholderData, page, pageCount, setSearchParams]);

  const goToPage = (nextPage: number) => {
    const bounded = Math.max(1, Math.min(pageCount, nextPage));
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      if (bounded === 1) next.delete("page");
      else next.set("page", String(bounded));
      return next;
    });
  };

  const submitPage = (event: FormEvent) => {
    event.preventDefault();
    const requested = Number(pageInput);
    if (Number.isFinite(requested)) goToPage(Math.trunc(requested));
    else setPageInput(String(page));
  };

  return (
    <div className="flex h-full">
      <div className="min-w-0 flex-1 overflow-y-auto scrollbar-thin">
        <div className="mx-auto max-w-5xl px-4 py-8">
          <h1 className="text-xl font-semibold text-[var(--color-text)]">Explore Laptops</h1>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            Browse the full laptop dataset with search, filters, and sorting.
          </p>

          <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-faint)]" />
              <input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Search by name or brand..."
                className="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] py-2.5 pl-9 pr-3 text-sm text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              />
            </div>
            <select
              value={sort}
              onChange={(e) => {
                const nextSort = e.target.value as SortOption;
                setSearchParams((current) => {
                  const next = new URLSearchParams(current);
                  next.set("sort", nextSort);
                  next.delete("page");
                  return next;
                });
              }}
              className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2.5 text-sm text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              {SORT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <button
              onClick={() => setFiltersOpen((v) => !v)}
              className={cn(
                "flex items-center gap-1.5 rounded-xl border px-3.5 py-2.5 text-sm font-medium transition-colors",
                filtersOpen
                  ? "border-[var(--color-accent)] bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                  : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
              )}
            >
              <SlidersHorizontal className="h-4 w-4" />
              Filters
              {activeFilterCount > 0 && (
                <span className="rounded-full bg-[var(--color-accent)] px-1.5 text-xs text-white">
                  {activeFilterCount}
                </span>
              )}
            </button>
          </div>

          <div className="mt-6">
            {isLoading ? (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-56 w-full rounded-2xl" />
                ))}
              </div>
            ) : isError ? (
              <EmptyState
                title="Could not load laptops"
                description={error instanceof Error ? error.message : "The catalog request failed."}
                action={
                  <button
                    type="button"
                    onClick={() => refetch()}
                    className="rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                  >
                    Retry
                  </button>
                }
              />
            ) : laptops && laptops.length > 0 ? (
              <div
                className={cn(
                  "grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 transition-opacity",
                  isPlaceholderData && "opacity-60"
                )}
              >
                {laptops.map((laptop) => (
                  <LaptopCard key={laptop.id} laptop={laptop} />
                ))}
              </div>
            ) : (
              <EmptyState
                title="No laptops found"
                description="Try a different search term or adjust your filters."
              />
            )}
          </div>

          {total > 0 && (
            <div className="mt-6 flex flex-col items-center justify-between gap-3 border-t border-[var(--color-border)] pt-4 sm:flex-row">
              <p className="text-xs text-[var(--color-text-muted)]">
                Showing <span className="font-medium text-[var(--color-text)]">{rangeStart}-{rangeEnd}</span> of{" "}
                <span className="font-medium text-[var(--color-text)]">{total.toLocaleString()}</span> laptops
              </p>
              <div className="flex flex-wrap items-center justify-center gap-1.5">
                <button
                  type="button"
                  onClick={() => goToPage(1)}
                  disabled={page <= 1}
                  aria-label="First page"
                  className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1.5 text-xs font-medium text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  First
                </button>
                <button
                  type="button"
                  onClick={() => goToPage(page - 1)}
                  disabled={page <= 1}
                  aria-label="Previous page"
                  className="flex items-center gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-[var(--color-surface)]"
                >
                  <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
                  Prev
                </button>
                {visiblePageNumbers(page, pageCount).map((pageNumber) => (
                  <button
                    key={pageNumber}
                    type="button"
                    onClick={() => goToPage(pageNumber)}
                    aria-label={`Page ${pageNumber}`}
                    aria-current={pageNumber === page ? "page" : undefined}
                    className={cn(
                      "min-w-8 rounded-lg border px-2 py-1.5 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]",
                      pageNumber === page
                        ? "border-[var(--color-accent)] bg-[var(--color-accent)] text-white"
                        : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
                    )}
                  >
                    {pageNumber}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => goToPage(page + 1)}
                  disabled={page >= pageCount}
                  aria-label="Next page"
                  className="flex items-center gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-[var(--color-surface)]"
                >
                  Next
                  <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
                <button
                  type="button"
                  onClick={() => goToPage(pageCount)}
                  disabled={page >= pageCount}
                  aria-label="Last page"
                  className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1.5 text-xs font-medium text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Last
                </button>
                <form onSubmit={submitPage} className="ml-1 flex items-center gap-1.5">
                  <label htmlFor="explore-page-number" className="text-xs text-[var(--color-text-muted)]">
                    Go to
                  </label>
                  <input
                    id="explore-page-number"
                    type="number"
                    min={1}
                    max={pageCount}
                    value={pageInput}
                    onChange={(event) => setPageInput(event.target.value)}
                    className="w-16 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1.5 text-xs text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                  />
                </form>
              </div>
            </div>
          )}
        </div>
      </div>

      {filtersOpen && (
        <div className="fixed inset-0 z-40 lg:static lg:z-auto lg:block lg:w-80 lg:flex-shrink-0">
          <div
            className="absolute inset-0 bg-black/40 lg:hidden"
            onClick={() => setFiltersOpen(false)}
            aria-hidden="true"
          />
          <div className="absolute right-0 top-0 h-full w-80 max-w-[85vw] border-l border-[var(--color-border)] bg-[var(--color-surface)] shadow-2xl lg:static lg:w-full lg:max-w-none lg:shadow-none">
            <FilterPanel
              filters={filters}
              onChange={(nextFilters) => {
                setFilters(nextFilters);
                goToPage(1);
              }}
              onClose={() => setFiltersOpen(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
