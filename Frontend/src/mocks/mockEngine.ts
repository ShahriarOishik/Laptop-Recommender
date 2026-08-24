import type {
  Laptop,
  LaptopFilters,
  LaptopRecommendation,
  MatchBreakdown,
  RequirementMatch,
  RetrievedEvidence,
} from "@/types/laptop";
import type { RagDebugInfo, RecommendationRequest, RecommendationResponse } from "@/types/chat";
import { MOCK_LAPTOPS } from "./laptops";
import { CATEGORY_REVIEW_SNIPPETS } from "./reviews";
import { USE_CASES } from "@/types/laptop";
import { calibrateMatchScore, vramToGb } from "@/lib/utils";

const mockGrounding = new Map<string, LaptopRecommendation[]>();

function mockConversationId(): string {
  return `mock-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function mockFollowUpAnswer(query: string, recommendations: LaptopRecommendation[]): string {
  const lower = query.toLowerCase();
  if (lower.includes("cheap")) {
    const cheapest = [...recommendations].sort(
      (a, b) => (a.laptop.price ?? Infinity) - (b.laptop.price ?? Infinity)
    )[0];
    return cheapest
      ? `${cheapest.laptop.name} is the cheapest laptop in your current grounded set at ${cheapest.laptop.price ? `$${cheapest.laptop.price.toLocaleString()}` : "an unavailable price"}. Use /suggest if you want me to retrieve different, cheaper options.`
      : "Use /suggest to create a grounded recommendation set first.";
  }
  if (lower.includes("ram")) {
    const mostRam = [...recommendations].sort(
      (a, b) => ramToGb(b.laptop.ram) - ramToGb(a.laptop.ram)
    )[0];
    return `${mostRam.laptop.name} has the most RAM in your current grounded set (${mostRam.laptop.ram ?? "capacity unavailable"}).`;
  }
  return `Based on your current grounded set, the leading option is ${recommendations[0].laptop.name}. I can compare these laptops by price, performance, memory, portability, or use case without retrieving new products.`;
}

interface ParsedRequirements {
  maxPrice?: number;
  minRam?: number;
  minStorage?: number;
  minVram?: number;
  wantsDedicatedGpu?: boolean;
  wantsNvidia?: boolean;
  wantsPortable?: boolean;
  wantsLongBattery?: boolean;
  useCases: string[];
}

function parseQuery(query: string, filters?: LaptopFilters): ParsedRequirements {
  const q = query.toLowerCase();

  const priceMatch = q.match(/(?:under|below|less than|<=?)\s*\$?\s*(\d{2,5})/);
  const ramMatch = q.match(/(\d{1,3})\s*\+?\s*gb\s*(?:of)?\s*ram/);
  const storageMatch = q.match(/(\d{2,4})\s*\+?\s*gb\s*(?:ssd|storage)/) ||
    q.match(/(\d{1,2})\s*tb\s*(?:ssd|storage)/);

  const useCases = USE_CASES.filter((uc) => q.includes(uc.toLowerCase())).slice();
  if (q.includes("gaming") && !useCases.includes("Gaming")) useCases.push("Gaming");
  if ((q.includes("coding") || q.includes("developer")) && !useCases.includes("Programming")) {
    useCases.push("Programming");
  }
  if ((q.includes("ml") || q.includes("ai") || q.includes("deep learning")) && !useCases.includes("Machine Learning")) {
    useCases.push("Machine Learning");
  }
  if (q.includes("college") || q.includes("university")) useCases.push("Student");

  return {
    maxPrice: filters?.maxPrice ?? (priceMatch ? Number(priceMatch[1]) : undefined),
    minRam: filters?.minRam ?? (ramMatch ? Number(ramMatch[1]) : undefined),
    minStorage:
      filters?.minStorage ??
      (storageMatch ? Number(storageMatch[1]) * (q.includes("tb") ? 1024 : 1) : undefined),
    minVram: filters?.minVram,
    wantsDedicatedGpu: q.includes("gpu") || q.includes("gaming") || q.includes("dedicated graphics"),
    wantsNvidia: q.includes("nvidia") || q.includes("rtx"),
    wantsPortable: q.includes("lightweight") || q.includes("portable") || q.includes("thin"),
    wantsLongBattery: q.includes("battery") || q.includes("long battery"),
    useCases: filters?.useCases?.length ? filters.useCases : useCases,
  };
}

export function ramToGb(ram?: string): number {
  if (!ram) return 0;
  const match = ram.match(/(\d+)/);
  return match ? Number(match[1]) : 0;
}

function storageToGb(storage?: string): number {
  if (!storage) return 0;
  const tbMatch = storage.match(/(\d+(?:\.\d+)?)\s*TB/i);
  if (tbMatch) return Number(tbMatch[1]) * 1024;
  const gbMatch = storage.match(/(\d+)\s*GB/i);
  return gbMatch ? Number(gbMatch[1]) : 0;
}

function hasDedicatedGpu(gpu?: string): boolean {
  if (!gpu) return false;
  return !gpu.toLowerCase().includes("integrated");
}

function isNvidia(gpu?: string): boolean {
  return !!gpu?.toLowerCase().includes("nvidia") || !!gpu?.toLowerCase().includes("rtx") || !!gpu?.toLowerCase().includes("gtx");
}

function batteryHours(battery?: string): number {
  if (!battery) return 0;
  const match = battery.match(/(\d+)/);
  return match ? Number(match[1]) : 0;
}

function weightKg(weight?: string): number {
  if (!weight) return 2.2;
  const match = weight.match(/(\d+(?:\.\d+)?)/);
  return match ? Number(match[1]) : 2.2;
}

interface ScoredLaptop {
  laptop: Laptop;
  score: number;
  hardConstraintsMet: boolean;
  breakdown: MatchBreakdown[];
  matched: RequirementMatch[];
}

function scoreLaptop(laptop: Laptop, req: ParsedRequirements): ScoredLaptop {
  const matched: RequirementMatch[] = [];
  let budgetScore = 1;
  let hardConstraintsMet = true;

  if (req.maxPrice !== undefined && laptop.price !== undefined) {
    if (laptop.price <= req.maxPrice) {
      budgetScore = 1;
      matched.push({ label: `Within your $${req.maxPrice} budget`, status: "met" });
    } else {
      const overBy = laptop.price - req.maxPrice;
      budgetScore = Math.max(0, 1 - overBy / req.maxPrice);
      hardConstraintsMet = false;
      matched.push({
        label: `Within your $${req.maxPrice} budget`,
        status: overBy / req.maxPrice < 0.15 ? "partial" : "unmet",
        detail: `$${overBy} over budget`,
      });
    }
  }

  let ramScore = 1;
  const ramGb = ramToGb(laptop.ram);
  if (req.minRam !== undefined) {
    if (ramGb >= req.minRam) {
      ramScore = 1;
      matched.push({ label: `${req.minRam} GB+ RAM requirement satisfied`, status: "met" });
    } else {
      ramScore = Math.max(0.2, ramGb / req.minRam);
      hardConstraintsMet = false;
      matched.push({
        label: `${req.minRam} GB+ RAM requirement satisfied`,
        status: "unmet",
        detail: `Only ${ramGb} GB available`,
      });
    }
  }

  let storageScore = 1;
  const storGb = storageToGb(laptop.storage);
  if (req.minStorage !== undefined) {
    if (storGb >= req.minStorage) {
      storageScore = 1;
    } else {
      storageScore = Math.max(0.3, storGb / req.minStorage);
      hardConstraintsMet = false;
    }
  }

  let gpuScore = 0.6;
  if (req.wantsNvidia) {
    gpuScore = isNvidia(laptop.gpu) ? 1 : 0.2;
    if (isNvidia(laptop.gpu)) {
      matched.push({ label: "Dedicated NVIDIA GPU", status: "met" });
    } else {
      hardConstraintsMet = false;
      matched.push({ label: "Dedicated NVIDIA GPU", status: "unmet", detail: laptop.gpu ?? "Not available" });
    }
  } else if (req.wantsDedicatedGpu) {
    gpuScore = hasDedicatedGpu(laptop.gpu) ? 1 : 0.3;
    matched.push({
      label: "Dedicated graphics",
      status: hasDedicatedGpu(laptop.gpu) ? "met" : "partial",
      detail: laptop.gpu ?? "Not available",
    });
  }
  if (req.minVram !== undefined) {
    const vram = vramToGb(laptop.gpu);
    const meetsVram = vram >= req.minVram;
    gpuScore = Math.min(gpuScore, meetsVram ? 1 : Math.max(0.1, vram / req.minVram));
    if (!meetsVram) hardConstraintsMet = false;
    matched.push({
      label: `${req.minVram} GB+ VRAM`,
      status: meetsVram ? "met" : "unmet",
      detail: vram > 0 ? `${vram} GB available` : "Dedicated VRAM not listed",
    });
  }

  let useCaseScore = 0.5;
  if (req.useCases.length > 0) {
    const overlap = req.useCases.filter((uc) =>
      laptop.categories?.some((c) => c.toLowerCase() === uc.toLowerCase())
    );
    useCaseScore = overlap.length / req.useCases.length;
    if (overlap.length > 0) {
      matched.push({ label: `Suited for ${overlap.join(", ")}`, status: "met" });
    } else {
      matched.push({ label: `Suited for ${req.useCases.join(", ")}`, status: "partial" });
    }
  }

  let portabilityScore = 0.6;
  if (req.wantsPortable) {
    const w = weightKg(laptop.weight);
    portabilityScore = w <= 1.5 ? 1 : w <= 1.9 ? 0.6 : 0.3;
    matched.push({
      label: "Lightweight / portable",
      status: portabilityScore >= 0.6 ? "met" : "partial",
      detail: laptop.weight ?? "Not available",
    });
  }

  let batteryScore = 0.6;
  if (req.wantsLongBattery) {
    const hrs = batteryHours(laptop.battery);
    batteryScore = hrs >= 12 ? 1 : hrs >= 8 ? 0.6 : 0.3;
    matched.push({
      label: "Long battery life",
      status: batteryScore >= 0.6 ? "met" : "partial",
      detail: laptop.battery ?? "Not available",
    });
  }

  const weighted =
    budgetScore * 0.28 +
    ramScore * 0.18 +
    storageScore * 0.1 +
    gpuScore * 0.2 +
    useCaseScore * 0.14 +
    portabilityScore * 0.05 +
    batteryScore * 0.05;

  const breakdown: MatchBreakdown[] = [
    { label: "Budget Match", value: Math.round(budgetScore * 100) },
    { label: "Performance", value: Math.round(((gpuScore + ramScore) / 2) * 100) },
    { label: "Battery", value: Math.round((req.wantsLongBattery ? batteryScore : Math.min(1, batteryHours(laptop.battery) / 14)) * 100) },
    { label: "Portability", value: Math.round(Math.max(0.2, 1 - (weightKg(laptop.weight) - 1) / 1.8) * 100) },
    { label: "Display", value: Math.round((laptop.display?.match(/OLED|165Hz|144Hz|240Hz|4K|QHD/i) ? 0.92 : 0.75) * 100) },
  ];

  return { laptop, score: Math.min(1, weighted), hardConstraintsMet, breakdown, matched };
}

function buildEvidence(laptop: Laptop, req: ParsedRequirements, score: number): RetrievedEvidence[] {
  const evidence: RetrievedEvidence[] = [
    {
      id: `${laptop.id}-spec`,
      source: "Laptop specification record",
      sourceType: "spec",
      text: `${laptop.cpu ?? "Not available"} · ${laptop.ram ?? "Not available"} · ${laptop.gpu ?? "Not available"} · ${laptop.storage ?? "Not available"}`,
      score: Math.min(0.99, score + 0.03),
    },
  ];

  const categoryKey =
    req.useCases.find((uc) => laptop.categories?.some((c) => c.toLowerCase() === uc.toLowerCase())) ??
    laptop.categories?.[0];

  if (categoryKey && CATEGORY_REVIEW_SNIPPETS[categoryKey]) {
    evidence.push({
      id: `${laptop.id}-review`,
      source: "Expert review excerpt",
      sourceType: "review",
      text: CATEGORY_REVIEW_SNIPPETS[categoryKey],
      score: Math.max(0.4, score - 0.08),
    });
  }

  return evidence;
}

function buildReasoning(laptop: Laptop, matched: RequirementMatch[]): string {
  const met = matched.filter((m) => m.status === "met").map((m) => m.label.toLowerCase());
  if (met.length === 0) {
    return `${laptop.name} is one of the closer matches available in the dataset, though it doesn't satisfy every requirement.`;
  }
  if (met.length === 1) {
    return `${laptop.name} stands out mainly because it is ${met[0]}.`;
  }
  const last = met[met.length - 1];
  const rest = met.slice(0, -1).join(", ");
  return `${laptop.name} is recommended because it is ${rest} and ${last}.`;
}

export async function mockGetRecommendations(
  request: RecommendationRequest
): Promise<RecommendationResponse> {
  const started = performance.now();
  const conversationId = request.conversationId ?? mockConversationId();
  if (!request.forceRetrieval) {
    const grounded = mockGrounding.get(conversationId) ?? [];
    if (grounded.length === 0) {
      return {
        answer: "I don't have a retrieved recommendation set yet. Use /suggest or apply filters first.",
        recommendations: [],
        retrievedContext: [],
        conversationId,
        intent: "general_question",
      };
    }
    return {
      answer: mockFollowUpAnswer(request.query, grounded),
      recommendations: grounded,
      retrievedContext: grounded.flatMap((item) => item.evidence ?? []),
      conversationId,
      intent: "follow_up",
    };
  }
  const req = parseQuery(request.query, request.filters);
  const topK = Math.min(20, Math.max(1, request.top_k ?? 5));

  const scored = MOCK_LAPTOPS.map((laptop) => scoreLaptop(laptop, req)).sort(
    (a, b) => b.score - a.score
  );

  const top = scored.slice(0, topK);
  const hasExactMatches = top.some((s) => s.hardConstraintsMet);

  const cheapestIdx = top.reduce(
    (bestIdx, cur, idx, arr) =>
      (cur.laptop.price ?? Infinity) < (arr[bestIdx].laptop.price ?? Infinity) ? idx : bestIdx,
    0
  );

  const recommendations: LaptopRecommendation[] = top.map((s, idx) => ({
    laptop: s.laptop,
    matchScore: Number(calibrateMatchScore(s.score).toFixed(2)),
    matchBreakdown: s.breakdown,
    reasoning: buildReasoning(s.laptop, s.matched),
    matchedRequirements: s.matched,
    evidence: buildEvidence(s.laptop, req, s.score),
    tier: idx === 0 ? "best-match" : idx === cheapestIdx ? "best-value" : "alternative",
  }));

  const retrievedContext = recommendations.flatMap((r) => r.evidence ?? []);

  const answer = hasExactMatches
    ? `I found ${recommendations.length} laptop${recommendations.length === 1 ? "" : "s"} that closely match your requirements.`
    : `I couldn't find a laptop that satisfies every requirement, but here are the closest matches from the current dataset.`;

  const retrievalLatencyMs = Math.round(18 + Math.random() * 20);
  const generationLatencyMs = Math.round(220 + Math.random() * 180);

  const debug: RagDebugInfo = {
    query: request.query,
    filters: request.filters,
    embeddingModel: "all-MiniLM-L6-v2 (mock)",
    faissIndexType: request.indexType ?? "ivf_flat",
    topK: recommendations.length,
    retrievedIds: recommendations.map((r) => r.laptop.id),
    retrievalLatencyMs,
    generationLatencyMs,
    totalLatencyMs: Math.round(performance.now() - started) + retrievalLatencyMs + generationLatencyMs,
  };

  await new Promise((resolve) => setTimeout(resolve, 700 + Math.random() * 500));

  mockGrounding.set(conversationId, recommendations);

  return {
    answer,
    recommendations,
    retrievedContext,
    hasExactMatches,
    debug,
    conversationId,
    intent: "new_recommendation",
  };
}
