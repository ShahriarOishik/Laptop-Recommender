import { useId, useRef, useState, type KeyboardEvent } from "react";
import { SendHorizontal, SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/common/Button";
import { cn } from "@/lib/utils";
import { isTypingCommandName, matchingCommands, parseSlashCommand, type SlashCommand } from "@/lib/slashCommands";
import { SlashCommandMenu, slashCommandOptionId } from "./SlashCommandMenu";

export interface SubmitOptions {
  forceRetrieval: boolean;
}

export function ChatInput({
  onSubmit,
  disabled,
  activeFilterCount,
  onToggleFilters,
}: {
  onSubmit: (value: string, options: SubmitOptions) => void;
  disabled?: boolean;
  activeFilterCount?: number;
  onToggleFilters?: () => void;
}) {
  const [value, setValue] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const menuId = useId();

  const matches = menuOpen ? matchingCommands(value) : [];

  const applyCommand = (command: SlashCommand) => {
    setValue(`/${command.name} `);
    setMenuOpen(false);
    setHighlightedIndex(0);
    textareaRef.current?.focus();
  };

  const handleChange = (raw: string) => {
    setValue(raw);
    setMenuOpen(isTypingCommandName(raw));
    setHighlightedIndex(0);
  };

  const submit = () => {
    if (disabled) return;
    const { command, text } = parseSlashCommand(value);
    if (command === "suggest") {
      // An empty query is fine as long as filters are set — the backend
      // then runs a pure metadata-filter search (no embedding involved) on
      // just those hard constraints, instead of padding the request with
      // filler text that would otherwise pollute semantic ranking with
      // noise. With no text AND no filters, there's nothing to search on.
      if (!text && !activeFilterCount) return;
      onSubmit(text, { forceRetrieval: true });
    } else {
      if (!text) return;
      onSubmit(text, { forceRetrieval: false });
    }
    setValue("");
    setMenuOpen(false);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (menuOpen && matches.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHighlightedIndex((i) => (i + 1) % matches.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setHighlightedIndex((i) => (i - 1 + matches.length) % matches.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        applyCommand(matches[highlightedIndex]);
        return;
      }
    }
    if (e.key === "Escape" && menuOpen) {
      e.preventDefault();
      setMenuOpen(false);
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const parsed = parseSlashCommand(value);
  const canSend =
    !disabled &&
    (parsed.command === "suggest"
      ? parsed.text.length > 0 || !!activeFilterCount
      : parsed.text.length > 0);

  return (
    <div className="relative rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-2 shadow-sm">
      {menuOpen && (
        <SlashCommandMenu
          id={menuId}
          commands={matches}
          highlightedIndex={highlightedIndex}
          onSelect={applyCommand}
        />
      )}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => handleChange(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={() => setMenuOpen(false)}
        disabled={disabled}
        rows={1}
        placeholder={
          disabled ? "Waiting for a response…" : "Ask a question, or type / for commands (e.g. /suggest)"
        }
        aria-label="Message LapWise AI. Type / to see available commands."
        role="combobox"
        aria-expanded={menuOpen}
        aria-controls={menuId}
        aria-activedescendant={
          menuOpen && matches[highlightedIndex] ? slashCommandOptionId(matches[highlightedIndex].name) : undefined
        }
        aria-autocomplete="list"
        autoComplete="off"
        className="max-h-32 w-full resize-none bg-transparent px-2.5 py-2 text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-faint)] focus:outline-none disabled:cursor-not-allowed"
      />
      <div className="flex items-center justify-between gap-2 px-1 pb-0.5">
        {onToggleFilters ? (
          <button
            type="button"
            onClick={onToggleFilters}
            aria-haspopup="dialog"
            className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
          >
            <SlidersHorizontal className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Filters</span>
            {!!activeFilterCount && (
              <span className="rounded-full bg-[var(--color-accent-soft)] px-1.5 text-[var(--color-accent)]">
                {activeFilterCount}
              </span>
            )}
          </button>
        ) : (
          <span />
        )}
        <Button
          size="sm"
          variant="primary"
          disabled={!canSend}
          onClick={submit}
          icon={<SendHorizontal className={cn("h-3.5 w-3.5")} />}
          aria-label="Send message"
        >
          Send
        </Button>
      </div>
    </div>
  );
}
