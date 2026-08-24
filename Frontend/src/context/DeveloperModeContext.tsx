import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import type { ApiIndexType } from "@/types/api";

const UNLOCKED_KEY = "lapwise-developer-unlocked";
const SETTINGS_KEY = "lapwise-developer-settings";

interface DeveloperSettings {
  indexType: ApiIndexType;
  topK: number;
}

interface DeveloperModeValue extends DeveloperSettings {
  isUnlocked: boolean;
  setIndexType: (indexType: ApiIndexType) => void;
  setTopK: (topK: number) => void;
  lock: () => void;
}

const DEFAULT_SETTINGS: DeveloperSettings = { indexType: "ivf_flat", topK: 5 };
const DeveloperModeContext = createContext<DeveloperModeValue | null>(null);

function readSettings(): DeveloperSettings {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(SETTINGS_KEY) ?? "null") as Partial<DeveloperSettings> | null;
    const topK = Math.min(20, Math.max(1, Number(parsed?.topK) || DEFAULT_SETTINGS.topK));
    return { indexType: parsed?.indexType ?? DEFAULT_SETTINGS.indexType, topK };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function DeveloperModeProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [isUnlocked, setIsUnlocked] = useState(() => sessionStorage.getItem(UNLOCKED_KEY) === "true");
  const [settings, setSettings] = useState(readSettings);

  const lock = useCallback(() => {
    sessionStorage.removeItem(UNLOCKED_KEY);
    sessionStorage.removeItem(SETTINGS_KEY);
    setIsUnlocked(false);
    setSettings({ ...DEFAULT_SETTINGS });
    navigate("/");
  }, [navigate]);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "d") {
        event.preventDefault();
        if (isUnlocked) {
          lock();
        } else {
          sessionStorage.setItem(UNLOCKED_KEY, "true");
          setIsUnlocked(true);
          navigate("/developer");
        }
      }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, [isUnlocked, lock, navigate]);

  useEffect(() => {
    sessionStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  }, [settings]);

  const value: DeveloperModeValue = {
    isUnlocked,
    ...settings,
    setIndexType: (indexType) => setSettings((current) => ({ ...current, indexType })),
    setTopK: (topK) =>
      setSettings((current) => ({ ...current, topK: Math.min(20, Math.max(1, Math.round(topK))) })),
    lock,
  };

  return <DeveloperModeContext.Provider value={value}>{children}</DeveloperModeContext.Provider>;
}

export function useDeveloperMode(): DeveloperModeValue {
  const value = useContext(DeveloperModeContext);
  if (!value) throw new Error("useDeveloperMode must be used within DeveloperModeProvider");
  return value;
}
