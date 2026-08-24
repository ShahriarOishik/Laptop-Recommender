import { useNavigate } from "react-router-dom";
import { GitCompare, MessageCircleQuestion, Minus, Plus } from "lucide-react";
import type { LaptopRecommendation } from "@/types/laptop";
import { formatPrice } from "@/lib/utils";
import { Badge } from "@/components/common/Badge";
import { Button } from "@/components/common/Button";
import { LaptopBadgeList } from "./LaptopBadge";
import { LaptopSpecs } from "./LaptopSpecs";
import { MatchScore } from "@/components/recommendations/MatchScore";
import { RequirementMatchList } from "@/components/recommendations/RequirementMatchList";
import { EvidencePanel } from "@/components/evidence/EvidencePanel";
import { ShortlistButton } from "@/components/shortlist/ShortlistButton";
import { useCompare } from "@/context/CompareContext";

const tierLabel: Record<NonNullable<LaptopRecommendation["tier"]>, string> = {
  "best-match": "Best Match",
  "best-value": "Best Value",
  alternative: "Alternative",
};

const tierTone: Record<NonNullable<LaptopRecommendation["tier"]>, "success" | "accent" | "neutral"> = {
  "best-match": "success",
  "best-value": "accent",
  alternative: "neutral",
};

export function LaptopRecommendationCard({
  recommendation,
  onAskAI,
  actionsDisabled,
}: {
  recommendation: LaptopRecommendation;
  onAskAI?: (laptop: LaptopRecommendation["laptop"]) => void;
  actionsDisabled?: boolean;
}) {
  const { laptop, matchScore, matchBreakdown, reasoning, matchedRequirements, evidence, tier, strengths, tradeoffs } =
    recommendation;
  const navigate = useNavigate();
  const { isComparing, toggleCompare, atLimit } = useCompare();
  const comparing = isComparing(laptop.id);

  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-[var(--color-text)]">{laptop.name}</h3>
            {tier && <Badge tone={tierTone[tier]}>{tierLabel[tier]}</Badge>}
          </div>
          <div className="mt-1.5">
            <LaptopBadgeList categories={laptop.categories} />
          </div>
        </div>
        <div className="flex flex-shrink-0 flex-col items-end gap-1">
          <MatchScore score={matchScore} breakdown={matchBreakdown} />
          <span className="text-base font-semibold text-[var(--color-text)]">
            {formatPrice(laptop.price)}
          </span>
        </div>
      </div>

      <div className="mt-4">
        <LaptopSpecs laptop={laptop} compact />
      </div>

      <div className="mt-4 rounded-xl bg-[var(--color-surface-2)] p-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-faint)]">
          Why this matches
        </p>
        <p className="mt-1 text-sm text-[var(--color-text)]">{reasoning}</p>
        {matchedRequirements && matchedRequirements.length > 0 && (
          <div className="mt-2.5">
            <RequirementMatchList items={matchedRequirements} />
          </div>
        )}
      </div>

      {((strengths && strengths.length > 0) || (tradeoffs && tradeoffs.length > 0)) && (
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {strengths && strengths.length > 0 && (
            <div>
              <p className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-[var(--color-success)]">
                <Plus className="h-3 w-3" /> Strengths
              </p>
              <ul className="mt-1 space-y-0.5 text-sm text-[var(--color-text)]">
                {strengths.map((item) => (
                  <li key={item}>• {item}</li>
                ))}
              </ul>
            </div>
          )}
          {tradeoffs && tradeoffs.length > 0 && (
            <div>
              <p className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-faint)]">
                <Minus className="h-3 w-3" /> Trade-offs
              </p>
              <ul className="mt-1 space-y-0.5 text-sm text-[var(--color-text-muted)]">
                {tradeoffs.map((item) => (
                  <li key={item}>• {item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" onClick={() => navigate(`/laptop/${laptop.id}`)}>
          Details
        </Button>
        <Button
          size="sm"
          variant={comparing ? "primary" : "secondary"}
          icon={<GitCompare className="h-3.5 w-3.5" />}
          disabled={!comparing && atLimit}
          onClick={() => toggleCompare(laptop)}
          aria-pressed={comparing}
          aria-label={comparing ? `Remove ${laptop.name} from comparison` : `Add ${laptop.name} to comparison`}
        >
          {comparing ? "In comparison" : "Compare"}
        </Button>
        <ShortlistButton laptop={laptop} />
        {onAskAI && (
          <Button
            size="sm"
            variant="ghost"
            icon={<MessageCircleQuestion className="h-3.5 w-3.5" />}
            disabled={actionsDisabled}
            onClick={() => onAskAI(laptop)}
          >
            Ask AI About This
          </Button>
        )}
      </div>

      <div className="mt-4">
        <EvidencePanel evidence={evidence} />
      </div>
    </div>
  );
}
