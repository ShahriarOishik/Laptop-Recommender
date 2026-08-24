import { useMemo } from "react";
import {
  Briefcase,
  Camera,
  Code2,
  Feather,
  Gamepad2,
  GraduationCap,
  Layers,
  Palette,
  Plane,
  Search,
  Server,
  Sparkles,
  Swords,
  Video,
  Wand2,
} from "lucide-react";
import { pickRandom } from "@/lib/utils";

const EXAMPLE_PROMPTS = [
  "Gaming laptop under $1,000",
  "Laptop for machine learning",
  "Best laptop for university",
  "Lightweight laptop with long battery",
  "Laptop for programming under $800",
  "RTX laptop for video editing",
  "Laptop for CUDA and deep learning workloads",
  "Budget laptop under $500",
  "Best laptop for competitive esports",
  "Laptop with the longest battery life",
  "Thin and light laptop for travel",
  "Laptop for Figma and UI design work",
  "16GB RAM laptop under $900",
  "Laptop for Python and data science",
  "Best value laptop for college students",
  "Laptop for photo editing in Lightroom",
  "Silent laptop with a great keyboard",
  "Laptop for coding on the go, under 1.5kg",
  "High refresh-rate laptop for gaming",
  "Laptop for 3D modeling and CAD",
  "Laptop for streaming and content creation",
  "Reliable business laptop with great security",
  "Laptop with the best display for creative work",
  "Laptop for running local LLMs",
];

const USE_CASE_SHORTCUTS = [
  { label: "Gaming", icon: Swords, prompt: "Recommend a gaming laptop" },
  { label: "Programming", icon: Code2, prompt: "Recommend a laptop for programming" },
  { label: "Machine Learning", icon: Sparkles, prompt: "Recommend a laptop for machine learning" },
  { label: "Student", icon: GraduationCap, prompt: "Recommend a laptop for a university student" },
  { label: "Business", icon: Briefcase, prompt: "Recommend a laptop for business use" },
  { label: "Content Creation", icon: Wand2, prompt: "Recommend a laptop for content creation" },
  { label: "Video Editing", icon: Video, prompt: "Recommend a laptop for video editing" },
  { label: "General Use", icon: Palette, prompt: "Recommend a laptop for general everyday use" },
  { label: "Photography", icon: Camera, prompt: "Recommend a laptop for photo editing" },
  { label: "Travel", icon: Plane, prompt: "Recommend a lightweight laptop for travel" },
  { label: "Esports", icon: Gamepad2, prompt: "Recommend a laptop for competitive esports" },
  { label: "3D & CAD", icon: Layers, prompt: "Recommend a laptop for 3D modeling and CAD" },
  { label: "Server / Dev Ops", icon: Server, prompt: "Recommend a laptop for running local servers and containers" },
  { label: "Ultraportable", icon: Feather, prompt: "Recommend the lightest, most portable laptop" },
];

export function SuggestedPrompts({ onSelect }: { onSelect: (prompt: string) => void }) {
  // Randomized once per time the empty state mounts (not on every render,
  // which would make the buttons jump around while someone's reading them).
  const prompts = useMemo(() => pickRandom(EXAMPLE_PROMPTS, 6), []);
  const shortcuts = useMemo(() => pickRandom(USE_CASE_SHORTCUTS, 8), []);

  return (
    <div className="space-y-6">
      <div>
        <p className="mb-2.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-faint)]">
          <Search className="h-3 w-3" aria-hidden="true" />
          Try a /suggest search
        </p>
        <div className="grid grid-cols-1 gap-2 xs:grid-cols-2">
          {prompts.map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => onSelect(prompt)}
              className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-left text-sm text-[var(--color-text)] transition-colors hover:border-[var(--color-accent)]/40 hover:bg-[var(--color-accent-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-faint)]">
          Browse by use case
        </p>
        <div className="flex flex-wrap gap-2">
          {shortcuts.map(({ label, icon: Icon, prompt }) => (
            <button
              key={label}
              type="button"
              onClick={() => onSelect(prompt)}
              className="flex items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-2 text-xs font-medium text-[var(--color-text-muted)] transition-colors hover:border-[var(--color-accent)]/40 hover:text-[var(--color-accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              <Icon className="h-3.5 w-3.5" aria-hidden="true" />
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
