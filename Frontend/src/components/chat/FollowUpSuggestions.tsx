const FOLLOW_UPS = [
  "Is this good for machine learning?",
  "Which one offers the best value?",
  "Which one has the best GPU?",
  "Which one has the longest battery life?",
  "What are the disadvantages of this laptop?",
  "Is this suitable for programming?",
  "Which is the most portable?",
  "Compare the first two.",
];

export function FollowUpSuggestions({
  onSelect,
  disabled,
}: {
  onSelect: (question: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {FOLLOW_UPS.map((q) => (
        <button
          key={q}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(q)}
          className="rounded-full bg-[var(--color-surface-2)] px-3 py-1.5 text-xs text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)] hover:text-[var(--color-accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {q}
        </button>
      ))}
    </div>
  );
}
