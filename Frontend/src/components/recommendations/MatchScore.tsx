import { useState } from "react";
import { ChevronDown } from "lucide-react";
import type { MatchBreakdown } from "@/types/laptop";
import { cn } from "@/lib/utils";

function scoreColor(pct: number) {
  if (pct >= 85) return "text-[var(--color-success)]";
  if (pct >= 65) return "text-[var(--color-accent)]";
  return "text-[var(--color-warning)]";
}

export function MatchScore({
  score,
  breakdown,
}: {
  score?: number;
  breakdown?: MatchBreakdown[];
}) {
  const [expanded, setExpanded] = useState(false);
  if (score === undefined) return null;
  const pct = Math.round(score * 100);

  return (
    <div className="text-right">
      <button
        onClick={() => breakdown && setExpanded((e) => !e)}
        className={cn(
          "flex items-center gap-1 text-sm font-semibold",
          scoreColor(pct),
          breakdown && "cursor-pointer"
        )}
        aria-expanded={expanded}
        aria-label={`Match score ${pct}%, ${breakdown ? "toggle breakdown" : ""}`}
      >
        {pct}% Match
        {breakdown && (
          <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", expanded && "rotate-180")} />
        )}
      </button>

      {expanded && breakdown && (
        <div className="mt-2 w-44 space-y-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-left">
          {breakdown.map((b) => (
            <div key={b.label} className="space-y-0.5">
              <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
                <span>{b.label}</span>
                <span>{b.value}%</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-border)]">
                <div
                  className="h-full rounded-full bg-[var(--color-accent)]"
                  style={{ width: `${b.value}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
