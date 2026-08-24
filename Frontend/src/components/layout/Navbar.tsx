import { Laptop, Menu, Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "@/context/ThemeContext";
import { cn } from "@/lib/utils";

const themeOptions = [
  { value: "light" as const, icon: Sun, label: "Light" },
  { value: "dark" as const, icon: Moon, label: "Dark" },
  { value: "system" as const, icon: Monitor, label: "System" },
];

export function Navbar({ onMenuClick }: { onMenuClick: () => void }) {
  const { preference, setPreference } = useTheme();

  return (
    <header className="flex h-14 flex-shrink-0 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] px-4">
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuClick}
          aria-label="Open navigation menu"
          className="rounded-lg p-1.5 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] lg:hidden"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--color-accent)] text-white">
            <Laptop className="h-4 w-4" />
          </div>
          <span className="text-sm font-semibold tracking-tight text-[var(--color-text)]">
            LapWise <span className="text-[var(--color-accent)]">AI</span>
          </span>
        </div>
      </div>

      <div
        role="radiogroup"
        aria-label="Theme"
        className="flex items-center gap-0.5 rounded-full border border-[var(--color-border)] bg-[var(--color-surface-2)] p-0.5"
      >
        {themeOptions.map(({ value, icon: Icon, label }) => (
          <button
            key={value}
            role="radio"
            aria-checked={preference === value}
            aria-label={`${label} theme`}
            onClick={() => setPreference(value)}
            className={cn(
              "flex h-7 w-7 items-center justify-center rounded-full transition-colors",
              preference === value
                ? "bg-[var(--color-surface)] text-[var(--color-accent)] shadow-sm"
                : "text-[var(--color-text-faint)] hover:text-[var(--color-text)]"
            )}
          >
            <Icon className="h-3.5 w-3.5" />
          </button>
        ))}
      </div>
    </header>
  );
}
