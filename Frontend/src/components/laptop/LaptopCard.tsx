import { useNavigate } from "react-router-dom";
import { GitCompare } from "lucide-react";
import type { Laptop } from "@/types/laptop";
import { formatPrice } from "@/lib/utils";
import { Button } from "@/components/common/Button";
import { LaptopBadgeList } from "./LaptopBadge";
import { LaptopSpecs } from "./LaptopSpecs";
import { ShortlistButton } from "@/components/shortlist/ShortlistButton";
import { useCompare } from "@/context/CompareContext";

export function LaptopCard({ laptop }: { laptop: Laptop }) {
  const navigate = useNavigate();
  const { isComparing, toggleCompare, atLimit } = useCompare();
  const comparing = isComparing(laptop.id);

  return (
    <div className="flex flex-col rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-[var(--color-text)]">{laptop.name}</h3>
          <p className="text-xs text-[var(--color-text-muted)]">{laptop.brand}</p>
        </div>
        <span className="flex-shrink-0 text-base font-semibold text-[var(--color-text)]">
          {formatPrice(laptop.price)}
        </span>
      </div>

      <div className="mt-2">
        <LaptopBadgeList categories={laptop.categories} />
      </div>

      <div className="mt-4">
        <LaptopSpecs laptop={laptop} compact />
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" onClick={() => navigate(`/laptop/${laptop.id}`)}>
          Details
        </Button>
        <Button
          size="sm"
          variant={comparing ? "primary" : "secondary"}
          icon={<GitCompare className="h-3.5 w-3.5" />}
          disabled={!comparing && atLimit}
          aria-pressed={comparing}
          aria-label={
            comparing
              ? `Remove ${laptop.name} from comparison`
              : `Add ${laptop.name} to comparison`
          }
          title={!comparing && atLimit ? "You can compare up to 4 laptops" : undefined}
          onClick={() => toggleCompare(laptop)}
        >
          {comparing ? "Remove" : "Compare"}
        </Button>
        <ShortlistButton laptop={laptop} />
      </div>
    </div>
  );
}
