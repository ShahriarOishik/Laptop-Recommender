import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import App from "./App.tsx";
import { ThemeProvider } from "@/context/ThemeContext";
import { ShortlistProvider } from "@/context/ShortlistContext";
import { CompareProvider } from "@/context/CompareContext";
import { ChatHistoryProvider } from "@/context/ChatHistoryContext";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { DeveloperModeProvider } from "@/context/DeveloperModeContext";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <ShortlistProvider>
            <CompareProvider>
              <ChatHistoryProvider>
                <BrowserRouter>
                  <DeveloperModeProvider>
                    <App />
                  </DeveloperModeProvider>
                </BrowserRouter>
              </ChatHistoryProvider>
            </CompareProvider>
          </ShortlistProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>
);
