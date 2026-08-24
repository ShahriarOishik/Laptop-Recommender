import { createContext, useContext, useState, type ReactNode } from "react";
import type { Laptop } from "@/types/laptop";

export const MAX_COMPARE = 4;

interface CompareContextValue {
  compareList: Laptop[];
  isComparing: (id: string) => boolean;
  addToCompare: (laptop: Laptop) => void;
  toggleCompare: (laptop: Laptop) => void;
  removeFromCompare: (id: string) => void;
  replaceInCompare: (index: number, laptop: Laptop) => void;
  swapCompare: (firstIndex: number, secondIndex: number) => void;
  clearCompare: () => void;
  atLimit: boolean;
}

const CompareContext = createContext<CompareContextValue | undefined>(undefined);

export function CompareProvider({ children }: { children: ReactNode }) {
  const [compareList, setCompareList] = useState<Laptop[]>([]);

  const isComparing = (id: string) => compareList.some((l) => l.id === id);

  const addToCompare = (laptop: Laptop) => {
    setCompareList((prev) => {
      if (prev.length >= MAX_COMPARE || prev.some((l) => l.id === laptop.id)) return prev;
      return [...prev, laptop];
    });
  };

  const toggleCompare = (laptop: Laptop) => {
    setCompareList((prev) => {
      if (prev.some((l) => l.id === laptop.id)) {
        return prev.filter((l) => l.id !== laptop.id);
      }
      if (prev.length >= MAX_COMPARE) return prev;
      return [...prev, laptop];
    });
  };

  const removeFromCompare = (id: string) => {
    setCompareList((prev) => prev.filter((l) => l.id !== id));
  };

  const replaceInCompare = (index: number, laptop: Laptop) => {
    setCompareList((prev) => {
      if (index < 0 || index >= prev.length) return prev;
      if (prev.some((item, itemIndex) => itemIndex !== index && item.id === laptop.id)) return prev;
      const next = [...prev];
      next[index] = laptop;
      return next;
    });
  };

  const swapCompare = (firstIndex: number, secondIndex: number) => {
    setCompareList((prev) => {
      if (
        firstIndex < 0 ||
        secondIndex < 0 ||
        firstIndex >= prev.length ||
        secondIndex >= prev.length ||
        firstIndex === secondIndex
      ) {
        return prev;
      }
      const next = [...prev];
      [next[firstIndex], next[secondIndex]] = [next[secondIndex], next[firstIndex]];
      return next;
    });
  };

  const clearCompare = () => setCompareList([]);

  return (
    <CompareContext.Provider
      value={{
        compareList,
        isComparing,
        addToCompare,
        toggleCompare,
        removeFromCompare,
        replaceInCompare,
        swapCompare,
        clearCompare,
        atLimit: compareList.length >= MAX_COMPARE,
      }}
    >
      {children}
    </CompareContext.Provider>
  );
}

export function useCompare() {
  const ctx = useContext(CompareContext);
  if (!ctx) throw new Error("useCompare must be used within CompareProvider");
  return ctx;
}
