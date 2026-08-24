import { Loader2 } from "lucide-react";

/** Route-level Suspense fallback for lazy-loaded pages — brief by design,
 * since these are small code-split chunks, not data loads. */
export function PageLoading() {
  return (
    <div
      className="flex h-full min-h-[240px] w-full items-center justify-center gap-2 text-sm text-[var(--color-text-muted)]"
      role="status"
      aria-live="polite"
    >
      <Loader2 className="h-4 w-4 animate-spin text-[var(--color-accent)]" aria-hidden="true" />
      Loading…
    </div>
  );
}
