import { useQuery } from "@tanstack/react-query";
import { SlidersHorizontal, X } from "lucide-react";
import type { LaptopFilters } from "@/types/laptop";
import { CPU_OPTIONS, DISPLAY_OPTIONS, RAM_OPTIONS, USE_CASES, VRAM_OPTIONS } from "@/types/laptop";
import { getAllBrands } from "@/services/laptopService";
import { Button } from "@/components/common/Button";
import { cn } from "@/lib/utils";

function titleCase(value: string): string {
  return value.replace(/\b\w/g, (c) => c.toUpperCase());
}

function toggleInArray<T>(arr: T[] | undefined, value: T): T[] {
  const current = arr ?? [];
  return current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
        active
          ? "border-[var(--color-accent)] bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
          : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
      )}
    >
      {children}
    </button>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2 border-b border-[var(--color-border)] py-4 first:pt-0 last:border-none">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-faint)]">
        {title}
      </h4>
      {children}
    </div>
  );
}

export function countActiveFilters(filters: LaptopFilters): number {
  let count = 0;
  if (filters.minPrice !== undefined) count++;
  if (filters.maxPrice !== undefined) count++;
  if (filters.strictBudget) count++;
  if (filters.minRam !== undefined) count++;
  if (filters.minStorage !== undefined) count++;
  if (filters.minVram !== undefined) count++;
  count += filters.useCases?.length ?? 0;
  count += filters.cpuBrand?.length ?? 0;
  count += filters.brands?.length ?? 0;
  count += filters.displaySize?.length ?? 0;
  count += filters.operatingSystem?.length ?? 0;
  return count;
}

export function FilterPanel({
  filters,
  onChange,
  onClose,
}: {
  filters: LaptopFilters;
  onChange: (filters: LaptopFilters) => void;
  onClose?: () => void;
}) {
  const { data: brands = [] } = useQuery({ queryKey: ["brands"], queryFn: getAllBrands, staleTime: Infinity });
  const activeCount = countActiveFilters(filters);

  const update = (patch: Partial<LaptopFilters>) => onChange({ ...filters, ...patch });

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
        <div id="filter-panel-heading" className="flex items-center gap-2 text-sm font-semibold text-[var(--color-text)]">
          <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
          Filters
          {activeCount > 0 && (
            <span className="rounded-full bg-[var(--color-accent-soft)] px-2 py-0.5 text-xs text-[var(--color-accent)]">
              {activeCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {activeCount > 0 && (
            <button
              onClick={() => onChange({})}
              className="text-xs font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
            >
              Clear all
            </button>
          )}
          {onClose && (
            <button
              onClick={onClose}
              aria-label="Close filters"
              className="rounded-lg p-1 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] lg:hidden"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin px-4">
        <Section title="Budget">
          <div className="flex items-center gap-2">
            <label className="sr-only" htmlFor="min-price">
              Minimum price
            </label>
            <input
              id="min-price"
              type="number"
              min={0}
              placeholder="Min"
              value={filters.minPrice ?? ""}
              onChange={(e) => update({ minPrice: e.target.value ? Number(e.target.value) : undefined })}
              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1.5 text-sm text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            />
            <span className="text-[var(--color-text-faint)]">–</span>
            <label className="sr-only" htmlFor="max-price">
              Maximum price
            </label>
            <input
              id="max-price"
              type="number"
              min={0}
              placeholder="Max"
              value={filters.maxPrice ?? ""}
              onChange={(e) => update({ maxPrice: e.target.value ? Number(e.target.value) : undefined })}
              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1.5 text-sm text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            />
          </div>
          <label className="mt-2 flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
            <input
              type="checkbox"
              checked={!!filters.strictBudget}
              onChange={(e) => update({ strictBudget: e.target.checked || undefined })}
              className="h-3.5 w-3.5 rounded border-[var(--color-border)] text-[var(--color-accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            />
            Strict budget (don't show laptops over budget)
          </label>
        </Section>

        <Section title="Use Case">
          <div className="flex flex-wrap gap-1.5">
            {USE_CASES.map((uc) => (
              <Chip
                key={uc}
                active={!!filters.useCases?.includes(uc)}
                onClick={() => update({ useCases: toggleInArray(filters.useCases, uc) })}
              >
                {uc}
              </Chip>
            ))}
          </div>
        </Section>

        <Section title="RAM">
          <div className="flex flex-wrap gap-1.5">
            {RAM_OPTIONS.map((ram) => (
              <Chip
                key={ram}
                active={filters.minRam === ram}
                onClick={() => update({ minRam: filters.minRam === ram ? undefined : ram })}
              >
                {ram} GB+
              </Chip>
            ))}
          </div>
        </Section>

        <Section title="Storage">
          <div className="flex flex-wrap gap-1.5">
            {[256, 512, 1024, 2048].map((gb) => (
              <Chip
                key={gb}
                active={filters.minStorage === gb}
                onClick={() => update({ minStorage: filters.minStorage === gb ? undefined : gb })}
              >
                {gb >= 1024 ? `${gb / 1024} TB+` : `${gb} GB+`}
              </Chip>
            ))}
          </div>
        </Section>

        <Section title="GPU">
          <p className="text-xs font-medium text-[var(--color-text-muted)]">Minimum VRAM</p>
          <div className="flex flex-wrap gap-1.5">
            {VRAM_OPTIONS.map((vram) => (
              <Chip
                key={vram}
                active={filters.minVram === vram}
                onClick={() => update({ minVram: filters.minVram === vram ? undefined : vram })}
              >
                {vram} GB+
              </Chip>
            ))}
          </div>
        </Section>

        <Section title="CPU">
          <div className="flex flex-wrap gap-1.5">
            {CPU_OPTIONS.map((cpu) => (
              <Chip
                key={cpu}
                active={!!filters.cpuBrand?.includes(cpu)}
                onClick={() => update({ cpuBrand: toggleInArray(filters.cpuBrand, cpu) })}
              >
                {cpu}
              </Chip>
            ))}
          </div>
        </Section>

        <Section title="Display">
          <div className="flex flex-wrap gap-1.5">
            {DISPLAY_OPTIONS.map((d) => (
              <Chip
                key={d}
                active={!!filters.displaySize?.includes(d)}
                onClick={() => update({ displaySize: toggleInArray(filters.displaySize, d) })}
              >
                {d}
              </Chip>
            ))}
          </div>
        </Section>

        <Section title="Brand">
          <div className="flex flex-wrap gap-1.5">
            {brands.map((brand) => (
              <Chip
                key={brand}
                active={!!filters.brands?.includes(brand)}
                onClick={() => update({ brands: toggleInArray(filters.brands, brand) })}
              >
                {titleCase(brand)}
              </Chip>
            ))}
          </div>
        </Section>
      </div>

      {onClose && (
        <div className="border-t border-[var(--color-border)] p-4 lg:hidden">
          <Button variant="primary" className="w-full" onClick={onClose}>
            Done
          </Button>
        </div>
      )}
    </div>
  );
}
