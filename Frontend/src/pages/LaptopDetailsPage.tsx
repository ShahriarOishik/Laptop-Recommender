import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, GitCompare } from "lucide-react";
import { getLaptopById, getSimilarLaptops } from "@/services/laptopService";
import { ramToGb } from "@/mocks/mockEngine";
import { CATEGORY_REVIEW_SNIPPETS } from "@/mocks/reviews";
import { formatPrice } from "@/lib/utils";
import { LaptopBadgeList } from "@/components/laptop/LaptopBadge";
import { LaptopSpecs } from "@/components/laptop/LaptopSpecs";
import { LaptopCard } from "@/components/laptop/LaptopCard";
import { ShortlistButton } from "@/components/shortlist/ShortlistButton";
import { Button } from "@/components/common/Button";
import { Skeleton } from "@/components/common/Skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { useCompare } from "@/context/CompareContext";

export function LaptopDetailsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { isComparing, toggleCompare, atLimit } = useCompare();

  const { data: laptop, isLoading } = useQuery({
    queryKey: ["laptop", id],
    queryFn: () => getLaptopById(id!),
    enabled: !!id,
  });

  const { data: similar } = useQuery({
    queryKey: ["similar", id],
    queryFn: () => getSimilarLaptops(id!),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8 space-y-4">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-40 w-full rounded-2xl" />
      </div>
    );
  }

  if (!laptop) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8">
        <EmptyState
          title="Laptop not found"
          description="This laptop may have been removed from the dataset."
          action={
            <Button variant="primary" onClick={() => navigate("/explore")}>
              Back to Explore
            </Button>
          }
        />
      </div>
    );
  }

  const limitations: string[] = [];
  const ramGb = ramToGb(laptop.ram);
  if (ramGb > 0 && ramGb <= 8) limitations.push("Limited RAM for heavy multitasking");
  const weightMatch = laptop.weight?.match(/(\d+(?:\.\d+)?)/);
  if (weightMatch && Number(weightMatch[1]) >= 2.3) limitations.push("Heavier than ultrabooks");
  const batteryMatch = laptop.battery?.match(/(\d+)/);
  if (batteryMatch && Number(batteryMatch[1]) <= 7) limitations.push("Moderate battery life");
  if (laptop.gpu?.toLowerCase().includes("integrated")) {
    limitations.push("No dedicated GPU for demanding graphics workloads");
  }

  const comparing = isComparing(laptop.id);

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <button
        onClick={() => navigate(-1)}
        className="mb-4 flex items-center gap-1.5 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
      >
        <ArrowLeft className="h-4 w-4" />
        Back
      </button>

      <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-[var(--color-text)]">{laptop.name}</h1>
            <p className="text-sm text-[var(--color-text-muted)]">{laptop.brand}</p>
            <div className="mt-2">
              <LaptopBadgeList categories={laptop.categories} />
            </div>
          </div>
          <span className="text-2xl font-semibold text-[var(--color-text)]">
            {formatPrice(laptop.price)}
          </span>
        </div>

        <div className="mt-6">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-faint)]">
            Specifications
          </h2>
          <div className="mt-3">
            <LaptopSpecs laptop={laptop} />
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          <Button
            variant={comparing ? "primary" : "secondary"}
            icon={<GitCompare className="h-4 w-4" />}
            disabled={!comparing && atLimit}
            onClick={() => toggleCompare(laptop)}
            aria-pressed={comparing}
            aria-label={
              comparing
                ? `Remove ${laptop.name} from comparison`
                : `Add ${laptop.name} to comparison`
            }
          >
            {comparing ? "Remove from Compare" : "Compare"}
          </Button>
          <ShortlistButton laptop={laptop} />
        </div>
      </div>

      {laptop.categories && laptop.categories.length > 0 && (
        <div className="mt-6 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h2 className="text-sm font-semibold text-[var(--color-text)]">Recommended For</h2>
          <ul className="mt-2 space-y-1">
            {laptop.categories.map((c) => (
              <li key={c} className="text-sm text-[var(--color-success)]">
                ✓ {c}
              </li>
            ))}
          </ul>

          {limitations.length > 0 && (
            <>
              <h2 className="mt-4 text-sm font-semibold text-[var(--color-text)]">
                Potential Limitations
              </h2>
              <ul className="mt-2 space-y-1">
                {limitations.map((l) => (
                  <li key={l} className="text-sm text-[var(--color-text-muted)]">
                    • {l}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {laptop.categories?.some((c) => CATEGORY_REVIEW_SNIPPETS[c]) && (
        <div className="mt-6 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h2 className="text-sm font-semibold text-[var(--color-text)]">Retrieved Reviews</h2>
          <div className="mt-2 space-y-2">
            {laptop.categories
              .filter((c) => CATEGORY_REVIEW_SNIPPETS[c])
              .slice(0, 2)
              .map((c) => (
                <p key={c} className="rounded-xl bg-[var(--color-surface-2)] p-3 text-sm text-[var(--color-text)]">
                  {CATEGORY_REVIEW_SNIPPETS[c]}
                </p>
              ))}
          </div>
        </div>
      )}

      {similar && similar.length > 0 && (
        <div className="mt-6">
          <h2 className="mb-3 text-sm font-semibold text-[var(--color-text)]">Similar Laptops</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {similar.map((l) => (
              <LaptopCard key={l.id} laptop={l} />
            ))}
          </div>
        </div>
      )}

      <p className="mt-6 text-xs text-[var(--color-text-faint)]">
        Ask the{" "}
        <Link to="/" className="text-[var(--color-accent)] hover:underline">
          AI assistant
        </Link>{" "}
        why this laptop was recommended for a more detailed, grounded explanation.
      </p>
    </div>
  );
}
