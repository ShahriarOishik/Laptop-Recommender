import { Zap } from "lucide-react";
import type { SlashCommand } from "@/lib/slashCommands";
import { cn } from "@/lib/utils";

export function slashCommandOptionId(name: string) {
  return `slash-command-option-${name}`;
}

export function SlashCommandMenu({
  id,
  commands,
  highlightedIndex,
  onSelect,
}: {
  id: string;
  commands: SlashCommand[];
  highlightedIndex: number;
  onSelect: (command: SlashCommand) => void;
}) {
  if (commands.length === 0) {
    return (
      <div
        id={id}
        role="listbox"
        aria-label="Slash commands"
        className="absolute bottom-full left-0 mb-2 w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-xs text-[var(--color-text-faint)] shadow-lg"
      >
        No matching commands.
      </div>
    );
  }

  return (
    <div
      id={id}
      role="listbox"
      aria-label="Slash commands"
      className="absolute bottom-full left-0 mb-2 w-full overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-lg"
    >
      <p className="border-b border-[var(--color-border)] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-faint)]">
        Commands
      </p>
      <ul>
        {commands.map((command, index) => (
          <li key={command.name}>
            <button
              type="button"
              id={slashCommandOptionId(command.name)}
              role="option"
              aria-selected={index === highlightedIndex}
              onMouseDown={(e) => {
                // mousedown (not click) so this fires before the textarea's
                // blur, otherwise the menu closes before onSelect runs.
                e.preventDefault();
                onSelect(command);
              }}
              className={cn(
                "flex w-full items-start gap-2.5 px-3 py-2.5 text-left transition-colors",
                index === highlightedIndex
                  ? "bg-[var(--color-accent-soft)]"
                  : "hover:bg-[var(--color-surface-2)]"
              )}
            >
              <Zap
                className={cn(
                  "mt-0.5 h-3.5 w-3.5 flex-shrink-0",
                  index === highlightedIndex ? "text-[var(--color-accent)]" : "text-[var(--color-text-faint)]"
                )}
              />
              <span className="min-w-0">
                <span className="block font-mono text-xs font-semibold text-[var(--color-text)]">
                  /{command.name}
                </span>
                <span className="block text-xs text-[var(--color-text-muted)]">{command.description}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
