export interface Laptop {
  id: string;
  name: string;
  brand?: string;
  price?: number;
  cpu?: string;
  ram?: string;
  storage?: string;
  gpu?: string;
  display?: string;
  battery?: string;
  weight?: string;
  operatingSystem?: string;
  imageUrl?: string;
  categories?: string[];
}

export interface RequirementMatch {
  label: string;
  status: "met" | "partial" | "unmet";
  detail?: string;
}

export interface RetrievedEvidence {
  id: string;
  source?: string;
  sourceType?: "spec" | "review";
  text: string;
  score?: number;
}

export interface MatchBreakdown {
  label: string;
  value: number;
}

export interface LaptopRecommendation {
  laptop: Laptop;
  matchScore?: number;
  matchBreakdown?: MatchBreakdown[];
  reasoning: string;
  matchedRequirements?: RequirementMatch[];
  evidence?: RetrievedEvidence[];
  tier?: "best-match" | "best-value" | "alternative";
  /** Short qualitative highlights grounded in the laptop's own metadata —
   * from the backend's card_insights (LLM-assisted or deterministic
   * fallback), never invented specifications. */
  strengths?: string[];
  tradeoffs?: string[];
}

export interface LaptopFilters {
  minPrice?: number;
  maxPrice?: number;
  minRam?: number;
  minStorage?: number;
  minVram?: number;
  cpuBrand?: string[];
  brands?: string[];
  useCases?: string[];
  displaySize?: string[];
  operatingSystem?: string[];
  /** When true, an exact budget with too few matches returns fewer results
   * instead of the backend automatically including slightly-over-budget
   * alternatives. Off by default, matching today's behavior. */
  strictBudget?: boolean;
  /** Which FAISS index type to search with. Undefined means "use the
   * backend's own default" — not sent as an explicit value until the user
   * picks one from the dropdown. Not a content filter (doesn't narrow
   * results), so it's excluded from countActiveFilters. */
  indexType?: string;
}

export const USE_CASES = [
  "Gaming",
  "Programming",
  "Machine Learning",
  "Student",
  "Office",
  "Business",
  "Graphic Design",
  "Video Editing",
  "Content Creation",
  "General Use",
] as const;

export const RAM_OPTIONS = [8, 16, 32, 64] as const;
export const STORAGE_OPTIONS = [256, 512, 1024, 2048] as const;
export const VRAM_OPTIONS = [2, 4, 6, 8, 12, 16] as const;
export const CPU_OPTIONS = ["Intel", "AMD", "Apple", "Any"] as const;
export const DISPLAY_OPTIONS = ['13"', '14"', '15"', '16"+'] as const;
