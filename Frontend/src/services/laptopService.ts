import type { Laptop, LaptopFilters } from "@/types/laptop";
import type {
  ApiIndexOption,
  ApiLaptopCatalogSort,
  ApiLaptopListItem,
  IndexSettingsResponseDTO,
  LaptopDetailResponseDTO,
  LaptopListResponseDTO,
  SimilarLaptopsResponseDTO,
} from "@/types/api";
import { apiFetch, USE_MOCK_API } from "./apiClient";
import { MOCK_LAPTOPS } from "@/mocks/laptops";
import { ramToGb } from "@/mocks/mockEngine";
import { formatLaptopName, vramToGb } from "@/lib/utils";

export type SortOption = ApiLaptopCatalogSort;

export const EXPLORE_PAGE_SIZE = 24;

export interface ExploreParams {
  search?: string;
  filters?: LaptopFilters;
  sort?: SortOption;
  /** 1-indexed. */
  page?: number;
}

export interface ExploreResult {
  items: Laptop[];
  total: number;
  page: number;
  pageSize: number;
}

function metadataString(record: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const value = record[key];
    if (value === null || value === undefined) continue;
    if (Array.isArray(value)) {
      if (value.length > 0) return value.join(", ");
      continue;
    }
    const text = String(value).trim();
    if (text) return text;
  }
  return undefined;
}

function toLaptop(item: ApiLaptopListItem): Laptop {
  const ramGb = item["ram_capacity_gb"];
  const storageGb = item["storage_capacity_gb"];
  const weightKg = item["weight_kg"];
  return {
    id: String(item.laptop_id),
    name: formatLaptopName(item.brand, item.model),
    brand: item.brand,
    price: item.price_usd ?? undefined,
    cpu: metadataString(item, "cpu_full"),
    ram: metadataString(item, "ram_full") ?? (typeof ramGb === "number" ? `${ramGb} GB` : undefined),
    storage:
      metadataString(item, "storage") ?? (typeof storageGb === "number" ? `${storageGb} GB` : undefined),
    gpu: metadataString(item, "gpu_full", "gpu_tags"),
    display: metadataString(item, "display_full"),
    battery: metadataString(item, "battery"),
    weight: typeof weightKg === "number" ? `${weightKg} kg` : metadataString(item, "weight_kg"),
    operatingSystem: metadataString(item, "os", "os_normalized"),
  };
}

function buildQuery(params: ExploreParams): string {
  const query = new URLSearchParams();
  if (params.search) query.set("search", params.search);
  const filters = params.filters;
  if (filters?.minPrice !== undefined) query.set("min_price_usd", String(filters.minPrice));
  if (filters?.maxPrice !== undefined) query.set("max_price_usd", String(filters.maxPrice));
  if (filters?.minRam !== undefined) query.set("min_ram_gb", String(filters.minRam));
  if (filters?.minStorage !== undefined) query.set("min_storage_gb", String(filters.minStorage));
  if (filters?.minVram !== undefined) query.set("min_vram_gb", String(filters.minVram));
  filters?.brands?.forEach((brand) => query.append("brands", brand.toLowerCase()));
  filters?.operatingSystem?.forEach((os) => query.append("operating_systems", os.toLowerCase()));
  query.set("sort", params.sort ?? "name");
  const page = Math.max(1, params.page ?? 1);
  query.set("limit", String(EXPLORE_PAGE_SIZE));
  query.set("offset", String((page - 1) * EXPLORE_PAGE_SIZE));
  return query.toString();
}

function matchesMockFilters(laptop: Laptop, filters?: LaptopFilters, search?: string): boolean {
  if (search && search.trim().length > 0) {
    const q = search.toLowerCase();
    const haystack = `${laptop.name} ${laptop.brand ?? ""}`.toLowerCase();
    if (!haystack.includes(q)) return false;
  }
  if (!filters) return true;
  if (filters.minPrice !== undefined && (laptop.price ?? 0) < filters.minPrice) return false;
  if (filters.maxPrice !== undefined && (laptop.price ?? 0) > filters.maxPrice) return false;
  if (filters.minRam !== undefined && ramToGb(laptop.ram) < filters.minRam) return false;
  if (filters.minVram !== undefined && vramToGb(laptop.gpu) < filters.minVram) return false;
  if (filters.brands?.length && !filters.brands.includes(laptop.brand ?? "")) return false;
  if (
    filters.useCases?.length &&
    !filters.useCases.some((uc) => laptop.categories?.some((c) => c.toLowerCase() === uc.toLowerCase()))
  ) {
    return false;
  }
  if (
    filters.cpuBrand?.length &&
    !filters.cpuBrand.some((brand) => brand === "Any" || laptop.cpu?.toLowerCase().includes(brand.toLowerCase()))
  ) {
    return false;
  }
  return true;
}

export async function listLaptops(params: ExploreParams = {}): Promise<ExploreResult> {
  const page = Math.max(1, params.page ?? 1);

  if (!USE_MOCK_API) {
    const response = await apiFetch<LaptopListResponseDTO>(`/laptops?${buildQuery(params)}`);
    return {
      items: response.items.map(toLaptop),
      total: response.total,
      page,
      pageSize: response.limit,
    };
  }

  await new Promise((resolve) => setTimeout(resolve, 250));
  let results = MOCK_LAPTOPS.filter((l) => matchesMockFilters(l, params.filters, params.search));

  const idTieBreak = (a: Laptop, b: Laptop) => Number(a.id) - Number(b.id);
  if ((params.sort ?? "name") === "name") {
    results = [...results].sort((a, b) => a.name.localeCompare(b.name) || idTieBreak(a, b));
  } else {
    const direction = params.sort === "price-asc" ? 1 : -1;
    results = [...results].sort((a, b) => {
      if (a.price === undefined) return b.price === undefined ? idTieBreak(a, b) : 1;
      if (b.price === undefined) return -1;
      return direction * (a.price - b.price) || idTieBreak(a, b);
    });
  }

  const total = results.length;
  const start = (page - 1) * EXPLORE_PAGE_SIZE;
  return { items: results.slice(start, start + EXPLORE_PAGE_SIZE), total, page, pageSize: EXPLORE_PAGE_SIZE };
}

export async function getLaptopById(id: string): Promise<Laptop | undefined> {
  if (!USE_MOCK_API) {
    try {
      const response = await apiFetch<LaptopDetailResponseDTO>(`/laptops/${id}`);
      return toLaptop(response.laptop);
    } catch {
      return undefined;
    }
  }
  await new Promise((resolve) => setTimeout(resolve, 150));
  return MOCK_LAPTOPS.find((l) => l.id === id);
}

export async function getSimilarLaptops(id: string): Promise<Laptop[]> {
  if (!USE_MOCK_API) {
    try {
      const response = await apiFetch<SimilarLaptopsResponseDTO>(`/laptops/${id}/similar?limit=3`);
      return response.similar.map(toLaptop);
    } catch {
      return [];
    }
  }
  const target = MOCK_LAPTOPS.find((l) => l.id === id);
  if (!target) return [];
  await new Promise((resolve) => setTimeout(resolve, 150));
  return MOCK_LAPTOPS.filter(
    (l) => l.id !== id && l.categories?.some((c) => target.categories?.includes(c))
  ).slice(0, 3);
}

let cachedFacets: LaptopListResponseDTO["facets"] | null = null;

export async function getAllBrands(): Promise<string[]> {
  if (!USE_MOCK_API) {
    if (!cachedFacets) {
      const response = await apiFetch<LaptopListResponseDTO>("/laptops?limit=1");
      cachedFacets = response.facets;
    }
    return cachedFacets.brands;
  }
  return Array.from(new Set(MOCK_LAPTOPS.map((l) => l.brand).filter((b): b is string => !!b))).sort();
}

let cachedIndexOptions: { options: ApiIndexOption[]; defaultIndex: string } | null = null;

/** Mock-mode fallback mirrors Backend/app/main.py's BENCHMARKS dict and
 * default_index so the dropdown looks the same with or without a real
 * backend running. */
const MOCK_INDEX_OPTIONS: ApiIndexOption[] = [
  { id: "flat", label: "Flat (Exact K-NN)", default: false, available: true, parameters: {}, benchmark: { recall_at_10: 1.0, p50_ms: 16.823 } },
  { id: "ivf_flat", label: "IVF Flat", default: true, available: true, parameters: {}, benchmark: { recall_at_10: 0.882, p50_ms: 1.467 } },
  { id: "pq", label: "Product Quantization", default: false, available: true, parameters: {}, benchmark: { recall_at_10: 0.7463, p50_ms: 4.691 } },
  { id: "ivf_pq", label: "IVF + PQ", default: false, available: true, parameters: {}, benchmark: { recall_at_10: 0.746, p50_ms: 2.315 } },
  { id: "hnsw", label: "HNSW Flat", default: false, available: true, parameters: {}, benchmark: { recall_at_10: 0.9938, p50_ms: 0.95 } },
];

export async function getIndexSettings(): Promise<{ options: ApiIndexOption[]; defaultIndex: string }> {
  if (!USE_MOCK_API) {
    if (!cachedIndexOptions) {
      const response = await apiFetch<IndexSettingsResponseDTO>("/settings/indexes");
      cachedIndexOptions = { options: response.indexes, defaultIndex: response.default_index };
    }
    return cachedIndexOptions;
  }
  return { options: MOCK_INDEX_OPTIONS, defaultIndex: "ivf_flat" };
}
