import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatPrice(price?: number) {
  if (price === undefined || price === null) return "Not available";
  return `$${price.toLocaleString()}`;
}

export function formatSpec(value?: string) {
  return value && value.trim().length > 0 ? value : "Not available";
}

export function formatLaptopName(brand: string, model: string) {
  const cleanBrand = brand.trim();
  const cleanModel = model.trim();
  if (!cleanBrand) return cleanModel;
  if (!cleanModel) return cleanBrand;

  const escapedBrand = cleanBrand.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`^${escapedBrand}(?:$|[\\s:–—-])`, "i").test(cleanModel)
    ? cleanModel
    : `${cleanBrand} ${cleanModel}`;
}

export function vramToGb(gpu?: string) {
  const match = gpu?.match(/(\d+(?:\.\d+)?)\s*(GB|MB)\s*VRAM\b/i);
  if (!match) return 0;
  const amount = Number(match[1]);
  return match[2].toLowerCase() === "mb" ? amount / 1024 : amount;
}

export function generateId(prefix = "id") {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * The underlying match score naturally compresses into a fairly narrow band
 * (roughly 0.6-0.9 for anything that clears the relevance threshold and
 * gets shown at all) — displaying it raw as "82% match" reads as mediocre
 * even for the strongest available result. Stretch it onto a more intuitive
 * display range with a monotonic power curve: ordering and relative gaps
 * are preserved (a higher score always displays higher), only the scale
 * changes. Shared by the real backend path and the mock engine so the same
 * underlying score always displays the same percentage in both — otherwise
 * demos/screenshots/manual QA done in mock mode (which needs no backend)
 * would show numbers real users never see.
 */
export function calibrateMatchScore(rawScore: number): number {
  const clamped = Math.max(0, Math.min(1, rawScore));
  return Math.pow(clamped, 0.4);
}

/** Fisher-Yates shuffle, returns a new array — never mutates `items`. */
export function shuffle<T>(items: readonly T[]): T[] {
  const result = items.slice();
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

/** A random subset of `count` items, order shuffled. Clamps to the input
 * length so callers don't need to check array size first. */
export function pickRandom<T>(items: readonly T[], count: number): T[] {
  return shuffle(items).slice(0, Math.min(count, items.length));
}

import type { LaptopFilters } from "@/types/laptop";

export function summarizeRequirements(query: string, filters?: LaptopFilters): string[] {
  const lines: string[] = [];
  if (filters?.maxPrice !== undefined) lines.push(`Budget ≤ $${filters.maxPrice}`);
  if (filters?.minPrice !== undefined) lines.push(`Budget ≥ $${filters.minPrice}`);
  if (filters?.minRam !== undefined) lines.push(`RAM ≥ ${filters.minRam} GB`);
  if (filters?.minStorage !== undefined) lines.push(`Storage ≥ ${filters.minStorage} GB`);
  if (filters?.minVram !== undefined) lines.push(`VRAM ≥ ${filters.minVram} GB`);
  if (filters?.useCases?.length) lines.push(`Use case: ${filters.useCases.join(", ")}`);
  if (filters?.cpuBrand?.length) lines.push(`CPU: ${filters.cpuBrand.join(", ")}`);
  if (filters?.brands?.length) lines.push(`Brand: ${filters.brands.join(", ")}`);
  if (lines.length === 0) lines.push(query);
  return lines;
}
