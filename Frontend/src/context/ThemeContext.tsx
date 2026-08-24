import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type ThemePreference = "light" | "dark" | "system";

interface ThemeContextValue {
  preference: ThemePreference;
  setPreference: (pref: ThemePreference) => void;
  resolvedTheme: "light" | "dark";
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);
const STORAGE_KEY = "lapwise-theme";

function getSystemTheme(): "light" | "dark" {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreference] = useState<ThemePreference>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return (stored as ThemePreference) ?? "system";
  });
  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">(() =>
    preference === "system" ? getSystemTheme() : (preference as "light" | "dark")
  );

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, preference);
    const applied = preference === "system" ? getSystemTheme() : preference;
    setResolvedTheme(applied);
    document.documentElement.classList.toggle("dark", applied === "dark");

    if (preference === "system") {
      const media = window.matchMedia("(prefers-color-scheme: dark)");
      const listener = () => {
        const next = getSystemTheme();
        setResolvedTheme(next);
        document.documentElement.classList.toggle("dark", next === "dark");
      };
      media.addEventListener("change", listener);
      return () => media.removeEventListener("change", listener);
    }
  }, [preference]);

  return (
    <ThemeContext.Provider value={{ preference, setPreference, resolvedTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
