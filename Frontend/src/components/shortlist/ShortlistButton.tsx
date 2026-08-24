import { Heart } from "lucide-react";
import type { Laptop } from "@/types/laptop";
import { useShortlist } from "@/context/ShortlistContext";
import { cn } from "@/lib/utils";

export function ShortlistButton({ laptop, className }: { laptop: Laptop; className?: string }) {
  const { isShortlisted, toggleShortlist } = useShortlist();
  const saved = isShortlisted(laptop.id);

  return (
    <button
      onClick={() => toggleShortlist(laptop)}
      aria-pressed={saved}
      aria-label={saved ? `Remove ${laptop.name} from shortlist` : `Save ${laptop.name} to shortlist`}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-medium transition-colors",
        saved
          ? "border-[var(--color-danger)]/30 bg-[var(--color-danger-soft)] text-[var(--color-danger)]"
          : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]",
        className
      )}
    >
      <Heart className={cn("h-3.5 w-3.5", saved && "fill-current")} />
      {saved ? "Saved" : "Save"}
    </button>
  );
}
