import { useDeferredValue, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import type { Laptop } from "@/types/laptop";
import { EXPLORE_PAGE_SIZE, listLaptops } from "@/services/laptopService";
import { formatPrice, formatSpec } from "@/lib/utils";
import { Modal } from "@/components/common/Modal";
import { Button } from "@/components/common/Button";
import { Skeleton } from "@/components/common/Skeleton";

interface CatalogPickerProps {
  open: boolean;
  onClose: () => void;
  selectedIds: Set<string>;
  replacingIndex: number | null;
  onSelect: (laptop: Laptop) => void;
}

export function CatalogPicker({
  open,
  onClose,
  selectedIds,
  replacingIndex,
  onSelect,
}: CatalogPickerProps) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const deferredSearch = useDeferredValue(search);

  useEffect(() => {
    setPage(1);
  }, [deferredSearch, replacingIndex]);

  const { data, isLoading, isPlaceholderData, isError } = useQuery({
    queryKey: ["compare-catalog", deferredSearch, page],
    queryFn: () => listLaptops({ search: deferredSearch, page }),
    enabled: open,
    placeholderData: (previous) => previous,
  });

  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / EXPLORE_PAGE_SIZE));
  const rangeStart = total === 0 ? 0 : (page - 1) * EXPLORE_PAGE_SIZE + 1;
  const rangeEnd = Math.min(page * EXPLORE_PAGE_SIZE, total);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={replacingIndex === null ? "Add a laptop to compare" : `Replace laptop ${replacingIndex + 1}`}
      wide
    >
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-faint)]"
          aria-hidden="true"
        />
        <label className="sr-only" htmlFor="compare-catalog-search">
          Search the laptop catalog
        </label>
        <input
          id="compare-catalog-search"
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search the entire catalog by name or brand..."
          autoFocus
          className="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] py-2.5 pl-9 pr-3 text-sm text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
        />
      </div>

      <div className="mt-4 min-h-72">
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="h-20 w-full rounded-xl" />
            ))}
          </div>
        ) : isError ? (
          <p role="alert" className="rounded-xl bg-[var(--color-danger-soft)] p-4 text-sm text-[var(--color-danger)]">
            The laptop catalog could not be loaded. Please try again.
          </p>
        ) : data?.items.length ? (
          <ul className={isPlaceholderData ? "space-y-2 opacity-60" : "space-y-2"}>
            {data.items.map((laptop) => {
              const selected = selectedIds.has(laptop.id);
              return (
                <li
                  key={laptop.id}
                  className="flex flex-col gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 sm:flex-row sm:items-center"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                      <p className="truncate text-sm font-semibold text-[var(--color-text)]">{laptop.name}</p>
                      <p className="text-sm font-semibold text-[var(--color-text)]">{formatPrice(laptop.price)}</p>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs text-[var(--color-text-muted)]">
                      {formatSpec(laptop.cpu)} · {formatSpec(laptop.ram)} · {formatSpec(laptop.gpu)}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant={selected ? "ghost" : "secondary"}
                    disabled={selected || isPlaceholderData}
                    onClick={() => onSelect(laptop)}
                    aria-label={
                      selected
                        ? `${laptop.name} is already selected for comparison`
                        : `${replacingIndex === null ? "Add" : "Replace with"} ${laptop.name}`
                    }
                    className="w-full sm:w-auto"
                  >
                    {selected ? "Selected" : replacingIndex === null ? "Add" : "Replace"}
                  </Button>
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="flex min-h-72 items-center justify-center text-center">
            <div>
              <p className="text-sm font-semibold text-[var(--color-text)]">No laptops found</p>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">Try a different name or brand.</p>
            </div>
          </div>
        )}
      </div>

      {total > 0 && (
        <div className="mt-4 flex flex-col items-center justify-between gap-3 border-t border-[var(--color-border)] pt-4 sm:flex-row">
          <p className="text-xs text-[var(--color-text-muted)]">
            Showing {rangeStart}-{rangeEnd} of {total.toLocaleString()}
          </p>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={page <= 1 || isPlaceholderData}
              aria-label="Previous catalog page"
              icon={<ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />}
            >
              Prev
            </Button>
            <span className="min-w-20 text-center text-xs font-medium text-[var(--color-text)]">
              {page} / {pageCount}
            </span>
            <Button
              size="sm"
              onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
              disabled={page >= pageCount || isPlaceholderData}
              aria-label="Next catalog page"
            >
              Next
              <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
