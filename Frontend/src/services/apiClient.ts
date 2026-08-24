/**
 * Central place that decides whether requests hit the real FastAPI backend
 * or the local mock engine. Defaults to the real backend; set
 * VITE_USE_MOCK_API=true in .env only for offline/demo work.
 */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
export const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API === "true";

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** No network call in this app had a timeout — a stalled backend (an
 * overloaded LLM provider, a stuck worker) meant `await fetch(...)` just
 * hung forever, permanently disabling the UI with no recovery short of a
 * page refresh. 60s gives real headroom over the backend's own documented
 * worst case (up to ~45s across the Groq/Gemini/OpenRouter fallback chain). */
export const DEFAULT_REQUEST_TIMEOUT_MS = 60_000;

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DEFAULT_REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });

    if (!response.ok) {
      throw new ApiError(`Request to ${path} failed with status ${response.status}`, response.status);
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(`Request to ${path} timed out after ${DEFAULT_REQUEST_TIMEOUT_MS / 1000}s.`);
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
