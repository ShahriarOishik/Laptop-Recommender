import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { ChatMessage, ChatSession } from "@/types/chat";
import { generateId } from "@/lib/utils";

interface ChatHistoryContextValue {
  sessions: ChatSession[];
  activeSessionId: string;
  activeSession: ChatSession;
  createSession: () => string;
  setActiveSessionId: (id: string) => void;
  addMessage: (sessionId: string, message: ChatMessage) => void;
  updateMessage: (sessionId: string, messageId: string, patch: Partial<ChatMessage>) => void;
  setSessionConversationId: (sessionId: string, conversationId: string) => void;
  deleteSession: (id: string) => void;
  /** Which sessions currently have a message in flight — scoped per
   * session (not one shared flag) so switching chats mid-response doesn't
   * lock the wrong session's input. */
  pendingSessionIds: Set<string>;
  markSessionSending: (sessionId: string) => void;
  clearSessionSending: (sessionId: string) => void;
}

const ChatHistoryContext = createContext<ChatHistoryContextValue | undefined>(undefined);
const STORAGE_KEY = "lapwise-chat-sessions";

function newSession(): ChatSession {
  return { id: generateId("session"), title: "New chat", messages: [], createdAt: Date.now() };
}

export function ChatHistoryProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      const parsed = stored ? (JSON.parse(stored) as ChatSession[]) : [];
      return parsed.length > 0 ? parsed : [newSession()];
    } catch {
      return [newSession()];
    }
  });
  const [activeSessionId, setActiveSessionId] = useState<string>(sessions[0].id);
  const [pendingSessionIds, setPendingSessionIds] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  }, [sessions]);

  const createSession = useCallback(() => {
    const session = newSession();
    setSessions((prev) => [session, ...prev]);
    setActiveSessionId(session.id);
    return session.id;
  }, []);

  const addMessage = useCallback((sessionId: string, message: ChatMessage) => {
    setSessions((prev) =>
      prev.map((s) => {
        if (s.id !== sessionId) return s;
        const title =
          s.title === "New chat" && message.role === "user" && message.text
            ? message.text.slice(0, 48)
            : s.title;
        return { ...s, title, messages: [...s.messages, message] };
      })
    );
  }, []);

  const updateMessage = useCallback((sessionId: string, messageId: string, patch: Partial<ChatMessage>) => {
    setSessions((prev) =>
      prev.map((s) =>
        s.id !== sessionId
          ? s
          : { ...s, messages: s.messages.map((m) => (m.id === messageId ? { ...m, ...patch } : m)) }
      )
    );
  }, []);

  const setSessionConversationId = useCallback((sessionId: string, conversationId: string) => {
    setSessions((prev) =>
      prev.map((s) => (s.id !== sessionId ? s : { ...s, conversationId }))
    );
  }, []);

  const deleteSession = useCallback(
    (id: string) => {
      setSessions((prev) => {
        const next = prev.filter((s) => s.id !== id);
        const result = next.length > 0 ? next : [newSession()];
        if (id === activeSessionId) setActiveSessionId(result[0].id);
        return result;
      });
    },
    [activeSessionId]
  );

  const markSessionSending = useCallback((sessionId: string) => {
    setPendingSessionIds((prev) => {
      const next = new Set(prev);
      next.add(sessionId);
      return next;
    });
  }, []);

  const clearSessionSending = useCallback((sessionId: string) => {
    setPendingSessionIds((prev) => {
      if (!prev.has(sessionId)) return prev;
      const next = new Set(prev);
      next.delete(sessionId);
      return next;
    });
  }, []);

  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? sessions[0];

  const value = useMemo(
    () => ({
      sessions,
      activeSessionId: activeSession.id,
      activeSession,
      createSession,
      setActiveSessionId,
      addMessage,
      updateMessage,
      setSessionConversationId,
      deleteSession,
      pendingSessionIds,
      markSessionSending,
      clearSessionSending,
    }),
    [
      sessions,
      activeSession,
      createSession,
      addMessage,
      updateMessage,
      setSessionConversationId,
      deleteSession,
      pendingSessionIds,
      markSessionSending,
      clearSessionSending,
    ]
  );

  return <ChatHistoryContext.Provider value={value}>{children}</ChatHistoryContext.Provider>;
}

export function useChatHistory() {
  const ctx = useContext(ChatHistoryContext);
  if (!ctx) throw new Error("useChatHistory must be used within ChatHistoryProvider");
  return ctx;
}
