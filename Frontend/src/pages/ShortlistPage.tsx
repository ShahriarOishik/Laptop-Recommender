import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Heart, Search, SlidersHorizontal } from "lucide-react";
import { useShortlist } from "@/context/ShortlistContext";
import { LaptopCard } from "@/components/laptop/LaptopCard";
import { EmptyState } from "@/components/common/EmptyState";
import { Button } from "@/components/common/Button";
import {
  countShortlistFilters,
  filterShortlist,
  type ShortlistFilters,
} from "@/components/shortlist/shortlistFilters";
import { cn } from "@/lib/utils";

const inputClass =
  "w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]";

export function ShortlistPage() {
  const { shortlist } = useShortlist();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<ShortlistFilters>({});
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filteredShortlist = filterShortlist(shortlist, search, filters);
  const activeFilterCount = countShortlistFilters(filters);
  const hasActiveQuery = search.trim().length > 0 || activeFilterCount > 0;
  const brands = Array.from(
    new Set(shortlist.map((laptop) => laptop.brand).filter((brand): brand is string => !!brand))
  ).sort((a, b) => a.localeCompare(b));
  const operatingSystems = Array.from(
    new Set(
      shortlist
        .map((laptop) => laptop.operatingSystem)
        .filter((operatingSystem): operatingSystem is string => !!operatingSystem)
    )
  ).sort((a, b) => a.localeCompare(b));

  const updateFilters = (patch: Partial<ShortlistFilters>) => setFilters((current) => ({ ...current, ...patch }));
  const clearFilters = () => {
    setSearch("");
    setFilters({});
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="text-xl font-semibold text-[var(--color-text)]">Shortlist</h1>
      <p className="mt-1 text-sm text-[var(--color-text-muted)]">Laptops you've saved for later.</p>

      {shortlist.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            icon={<Heart className="h-8 w-8" />}
            title="No laptops saved yet"
            description="Save laptops from your chat recommendations or the Explore page to compare and revisit them later."
            action={
              <Button variant="primary" onClick={() => navigate("/")}>
                Start Chatting
              </Button>
            }
          />
        </div>
      ) : (
        <>
          <div className="mt-5 flex gap-2">
            <div className="relative flex-1">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-faint)]"
                aria-hidden="true"
              />
              <label className="sr-only" htmlFor="shortlist-search">Search shortlisted laptops</label>
              <input
                id="shortlist-search"
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search name, brand, CPU, or GPU..."
                className={cn(inputClass, "pl-9")}
              />
            </div>
            <Button
              onClick={() => setFiltersOpen((open) => !open)}
              aria-expanded={filtersOpen}
              aria-controls="shortlist-filters"
              icon={<SlidersHorizontal className="h-4 w-4" aria-hidden="true" />}
              className="md:hidden"
            >
              Filters
              {activeFilterCount > 0 && (
                <span className="rounded-full bg-[var(--color-accent)] px-1.5 text-[11px] text-white">
                  {activeFilterCount}
                </span>
              )}
            </Button>
          </div>

          <div
            id="shortlist-filters"
            className={cn(
              "mt-3 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4",
              filtersOpen ? "block" : "hidden md:block"
            )}
          >
            <div className="mb-3 flex items-center justify-between md:hidden">
              <p className="text-sm font-semibold text-[var(--color-text)]">Filters</p>
              {activeFilterCount > 0 && (
                <button onClick={() => setFilters({})} className="text-xs font-medium text-[var(--color-accent)]">
                  Clear filters
                </button>
              )}
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-6">
              <label className="text-xs font-medium text-[var(--color-text-muted)]">
                Brand
                <select
                  value={filters.brand ?? ""}
                  onChange={(event) => updateFilters({ brand: event.target.value || undefined })}
                  className={cn(inputClass, "mt-1")}
                >
                  <option value="">All brands</option>
                  {brands.map((brand) => <option key={brand} value={brand}>{brand}</option>)}
                </select>
              </label>
              <label className="text-xs font-medium text-[var(--color-text-muted)]">
                Minimum price
                <input
                  type="number"
                  min={0}
                  value={filters.minPrice ?? ""}
                  onChange={(event) => updateFilters({ minPrice: event.target.value ? Number(event.target.value) : undefined })}
                  placeholder="No minimum"
                  className={cn(inputClass, "mt-1")}
                />
              </label>
              <label className="text-xs font-medium text-[var(--color-text-muted)]">
                Maximum price
                <input
                  type="number"
                  min={0}
                  value={filters.maxPrice ?? ""}
                  onChange={(event) => updateFilters({ maxPrice: event.target.value ? Number(event.target.value) : undefined })}
                  placeholder="No maximum"
                  className={cn(inputClass, "mt-1")}
                />
              </label>
              <label className="text-xs font-medium text-[var(--color-text-muted)]">
                Minimum RAM
                <select
                  value={filters.minRam ?? ""}
                  onChange={(event) => updateFilters({ minRam: event.target.value ? Number(event.target.value) : undefined })}
                  className={cn(inputClass, "mt-1")}
                >
                  <option value="">Any RAM</option>
                  {[8, 16, 32, 64].map((ram) => <option key={ram} value={ram}>{ram} GB+</option>)}
                </select>
              </label>
              <label className="text-xs font-medium text-[var(--color-text-muted)]">
                Minimum storage
                <select
                  value={filters.minStorage ?? ""}
                  onChange={(event) => updateFilters({ minStorage: event.target.value ? Number(event.target.value) : undefined })}
                  className={cn(inputClass, "mt-1")}
                >
                  <option value="">Any storage</option>
                  {[256, 512, 1024, 2048].map((storage) => (
                    <option key={storage} value={storage}>
                      {storage >= 1024 ? `${storage / 1024} TB+` : `${storage} GB+`}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-xs font-medium text-[var(--color-text-muted)]">
                Operating system
                <select
                  value={filters.operatingSystem ?? ""}
                  onChange={(event) => updateFilters({ operatingSystem: event.target.value || undefined })}
                  className={cn(inputClass, "mt-1")}
                >
                  <option value="">All systems</option>
                  {operatingSystems.map((os) => <option key={os} value={os}>{os}</option>)}
                </select>
              </label>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-[var(--color-text-muted)]" aria-live="polite">
              Showing <span className="font-semibold text-[var(--color-text)]">{filteredShortlist.length}</span> of{" "}
              <span className="font-semibold text-[var(--color-text)]">{shortlist.length}</span> saved laptops
            </p>
            {hasActiveQuery && (
              <Button size="sm" variant="ghost" onClick={clearFilters}>Clear search and filters</Button>
            )}
          </div>

          {filteredShortlist.length > 0 ? (
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {filteredShortlist.map((laptop) => (
                <LaptopCard key={laptop.id} laptop={laptop} />
              ))}
            </div>
          ) : (
            <div className="mt-4">
              <EmptyState
                icon={<Search className="h-8 w-8" />}
                title="No saved laptops match"
                description="Try changing your search or clearing one or more filters."
                action={<Button variant="primary" onClick={clearFilters}>Clear search and filters</Button>}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}
