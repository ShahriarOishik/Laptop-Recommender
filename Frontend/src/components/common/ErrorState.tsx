import { AlertTriangle } from "lucide-react";
import { Button } from "./Button";

export function ErrorState({
  message = "We couldn't retrieve recommendations right now.",
  onRetry,
}: {
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-[var(--color-border)] bg-[var(--color-danger-soft)]/40 px-6 py-8 text-center">
      <AlertTriangle className="h-6 w-6 text-[var(--color-danger)]" />
      <p className="text-sm font-medium text-[var(--color-text)]">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try Again
        </Button>
      )}
    </div>
  );
}
