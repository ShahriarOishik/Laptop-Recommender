export function visiblePageNumbers(page: number, pageCount: number): number[] {
  const visibleCount = Math.min(5, pageCount);
  const start = Math.max(1, Math.min(page - 2, pageCount - visibleCount + 1));
  return Array.from({ length: visibleCount }, (_, index) => start + index);
}
