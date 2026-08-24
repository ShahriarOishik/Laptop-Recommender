import type { Laptop } from "@/types/laptop";

export interface ShortlistFilters {
  brand?: string;
  minPrice?: number;
  maxPrice?: number;
  minRam?: number;
  minStorage?: number;
  operatingSystem?: string;
}

export function capacityToGb(value?: string): number | undefined {
  if (!value) return undefined;
  const capacities = Array.from(value.matchAll(/(\d+(?:\.\d+)?)\s*(TB|GB)/gi), (match) => {
    const amount = Number(match[1]);
    return match[2].toUpperCase() === "TB" ? amount * 1024 : amount;
  });
  return capacities.length > 0 ? Math.max(...capacities) : undefined;
}

export function countShortlistFilters(filters: ShortlistFilters): number {
  return Object.values(filters).filter((value) => value !== undefined && value !== "").length;
}

export function filterShortlist(
  laptops: Laptop[],
  search: string,
  filters: ShortlistFilters
): Laptop[] {
  const query = search.trim().toLowerCase();

  return laptops.filter((laptop) => {
    if (query) {
      const searchable = [laptop.name, laptop.brand, laptop.cpu, laptop.gpu]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      if (!searchable.includes(query)) return false;
    }

    if (filters.brand && laptop.brand?.toLowerCase() !== filters.brand.toLowerCase()) return false;
    if (filters.operatingSystem && laptop.operatingSystem?.toLowerCase() !== filters.operatingSystem.toLowerCase()) {
      return false;
    }
    if (filters.minPrice !== undefined && (laptop.price === undefined || laptop.price < filters.minPrice)) {
      return false;
    }
    if (filters.maxPrice !== undefined && (laptop.price === undefined || laptop.price > filters.maxPrice)) {
      return false;
    }
    if (filters.minRam !== undefined && (capacityToGb(laptop.ram) ?? 0) < filters.minRam) return false;
    if (filters.minStorage !== undefined && (capacityToGb(laptop.storage) ?? 0) < filters.minStorage) {
      return false;
    }
    return true;
  });
}
