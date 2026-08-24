import { NavLink, useNavigate } from "react-router-dom";
import { Compass, GitCompare, Heart, MessageSquare, Plus, Trash2, Terminal } from "lucide-react";
import { useChatHistory } from "@/context/ChatHistoryContext";
import { useCompare } from "@/context/CompareContext";
import { useDeveloperMode } from "@/context/DeveloperModeContext";
import { cn } from "@/lib/utils";

const navItems = [
  { to: "/", label: "Chat", icon: MessageSquare, end: true },
  { to: "/explore", label: "Explore", icon: Compass, end: false },
  { to: "/compare", label: "Compare", icon: GitCompare, end: false },
  { to: "/shortlist", label: "Shortlist", icon: Heart, end: false },
];

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { sessions, activeSessionId, setActiveSessionId, createSession, deleteSession } =
    useChatHistory();
  const { compareList } = useCompare();
  const { isUnlocked } = useDeveloperMode();
  const navigate = useNavigate();

  const handleNewChat = () => {
    createSession();
    navigate("/");
    onNavigate?.();
  };

  const handleSelectSession = (id: string) => {
    setActiveSessionId(id);
    navigate("/");
    onNavigate?.();
  };

  return (
    <div className="flex h-full flex-col">
      <div className="px-3 pt-3">
        <button
          type="button"
          onClick={handleNewChat}
          className="flex w-full items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2.5 text-sm font-medium text-[var(--color-text)] transition-colors hover:bg-[var(--color-surface-2)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
        >
          <Plus className="h-4 w-4" />
          New Chat
        </button>
      </div>

      <nav aria-label="Primary" className="mt-3 space-y-0.5 px-3">
        {navItems.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]",
                isActive
                  ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                  : "text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text)]"
              )
            }
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
            {label}
            {to === "/compare" && compareList.length > 0 && (
              <span
                className="ml-auto min-w-5 rounded-full bg-[var(--color-accent-soft)] px-1.5 py-0.5 text-center text-[11px] font-semibold text-[var(--color-accent)]"
                aria-label={`${compareList.length} laptops selected for comparison`}
              >
                {compareList.length}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="mt-5 flex-1 overflow-y-auto scrollbar-thin px-3 pb-3">
        <p className="px-3 pb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-faint)]">
          Recent
        </p>
        <div className="space-y-0.5">
          {sessions
            .filter((s) => s.messages.length > 0 || s.id === activeSessionId)
            .map((session) => (
              <div
                key={session.id}
                className={cn(
                  "group flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm transition-colors",
                  session.id === activeSessionId
                    ? "bg-[var(--color-surface-2)] text-[var(--color-text)]"
                    : "text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text)]"
                )}
              >
                <button
                  type="button"
                  onClick={() => handleSelectSession(session.id)}
                  className="min-w-0 flex-1 truncate text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] rounded"
                  title={session.title}
                >
                  {session.title}
                </button>
                <button
                  type="button"
                  onClick={() => deleteSession(session.id)}
                  aria-label={`Delete chat: ${session.title}`}
                  className="rounded p-1 text-[var(--color-text-faint)] opacity-0 hover:text-[var(--color-danger)] focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] group-hover:opacity-100 group-focus-within:opacity-100"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
        </div>
      </div>

      {isUnlocked && <div className="border-t border-[var(--color-border)] px-3 py-3">
        <NavLink
          to="/developer"
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium transition-colors",
              isActive
                ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                : "text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text)]"
            )
          }
        >
          <Terminal className="h-4 w-4" />
          Developer Mode
        </NavLink>
      </div>}
    </div>
  );
}
