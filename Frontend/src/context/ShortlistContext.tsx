import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { Laptop } from "@/types/laptop";

interface ShortlistContextValue {
  shortlist: Laptop[];
  isShortlisted: (id: string) => boolean;
  toggleShortlist: (laptop: Laptop) => void;
  removeFromShortlist: (id: string) => void;
}

const ShortlistContext = createContext<ShortlistContextValue | undefined>(undefined);
const STORAGE_KEY = "lapwise-shortlist";

export function ShortlistProvider({ children }: { children: ReactNode }) {
  const [shortlist, setShortlist] = useState<Laptop[]>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored ? (JSON.parse(stored) as Laptop[]) : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(shortlist));
  }, [shortlist]);

  const isShortlisted = (id: string) => shortlist.some((l) => l.id === id);

  const toggleShortlist = (laptop: Laptop) => {
    setShortlist((prev) =>
      prev.some((l) => l.id === laptop.id) ? prev.filter((l) => l.id !== laptop.id) : [...prev, laptop]
    );
  };

  const removeFromShortlist = (id: string) => {
    setShortlist((prev) => prev.filter((l) => l.id !== id));
  };

  return (
    <ShortlistContext.Provider value={{ shortlist, isShortlisted, toggleShortlist, removeFromShortlist }}>
      {children}
    </ShortlistContext.Provider>
  );
}

export function useShortlist() {
  const ctx = useContext(ShortlistContext);
  if (!ctx) throw new Error("useShortlist must be used within ShortlistProvider");
  return ctx;
}
