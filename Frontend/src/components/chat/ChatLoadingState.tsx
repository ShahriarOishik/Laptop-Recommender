import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { RecommendationCardSkeleton } from "@/components/common/Skeleton";

const STAGES = [
  "Understanding requirements...",
  "Searching laptops...",
  "Preparing recommendations...",
];

export function ChatLoadingState() {
  const [stageIndex, setStageIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setStageIndex((i) => Math.min(i + 1, STAGES.length - 1));
    }, 900);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
        <Loader2 className="h-4 w-4 animate-spin text-[var(--color-accent)]" />
        {STAGES[stageIndex]}
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <RecommendationCardSkeleton />
        <RecommendationCardSkeleton />
      </div>
    </div>
  );
}
