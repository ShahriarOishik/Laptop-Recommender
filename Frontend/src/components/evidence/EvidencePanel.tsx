import { useState } from "react";
import { ChevronDown, FileText, MessageSquareQuote } from "lucide-react";
import type { RetrievedEvidence } from "@/types/laptop";
import { cn } from "@/lib/utils";

function EvidenceCard({ evidence }: { evidence: RetrievedEvidence }) {
  const Icon = evidence.sourceType === "review" ? MessageSquareQuote : FileText;
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-muted)]">
          <Icon className="h-3.5 w-3.5" />
          {evidence.source ?? "Retrieved source"}
        </div>
        {evidence.score !== undefined && (
          <span className="text-[11px] text-[var(--color-text-faint)]">
            Similarity: {evidence.score.toFixed(2)}
          </span>
        )}
      </div>
      <p className="mt-1.5 text-sm text-[var(--color-text)]">{evidence.text}</p>
    </div>
  );
}

export function EvidencePanel({ evidence }: { evidence?: RetrievedEvidence[] }) {
  const [open, setOpen] = useState(false);
  if (!evidence || evidence.length === 0) return null;

  return (
    <div className="border-t border-[var(--color-border)] pt-3">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex items-center gap-1.5 text-xs font-semibold text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
      >
        Sources Used for This Recommendation
        <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-2.5 space-y-2">
          {evidence.map((e) => (
            <EvidenceCard key={e.id} evidence={e} />
          ))}
        </div>
      )}
    </div>
  );
}
