import { Check, Minus, X } from "lucide-react";
import type { RequirementMatch } from "@/types/laptop";
import { cn } from "@/lib/utils";

const statusConfig = {
  met: { icon: Check, className: "text-[var(--color-success)]" },
  partial: { icon: Minus, className: "text-[var(--color-warning)]" },
  unmet: { icon: X, className: "text-[var(--color-danger)]" },
};

export function RequirementMatchList({ items }: { items?: RequirementMatch[] }) {
  if (!items || items.length === 0) return null;

  return (
    <ul className="space-y-1.5">
      {items.map((item, idx) => {
        const { icon: Icon, className } = statusConfig[item.status];
        return (
          <li key={idx} className="flex items-start gap-2 text-sm">
            <Icon className={cn("mt-0.5 h-3.5 w-3.5 flex-shrink-0", className)} aria-hidden="true" />
            <span className="text-[var(--color-text)]">
              {item.label}
              {item.detail && (
                <span className="text-[var(--color-text-muted)]"> — {item.detail}</span>
              )}
            </span>
            <span className="sr-only">
              ({item.status === "met" ? "met" : item.status === "partial" ? "partially met" : "not met"})
            </span>
          </li>
        );
      })}
    </ul>
  );
}
