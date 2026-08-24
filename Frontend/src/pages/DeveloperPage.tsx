import { useQuery } from "@tanstack/react-query";
import { Lock, Settings2, Terminal } from "lucide-react";
import { useChatHistory } from "@/context/ChatHistoryContext";
import { useDeveloperMode } from "@/context/DeveloperModeContext";
import { USE_MOCK_API } from "@/services/apiClient";
import { getIndexSettings } from "@/services/laptopService";
import type { ApiIndexType } from "@/types/api";
import { Badge } from "@/components/common/Badge";
import { Button } from "@/components/common/Button";
import { EmptyState } from "@/components/common/EmptyState";

function Row({ label, value }: { label: string; value?: string | number }) {
  return (
    <div className="flex flex-col gap-1 border-b border-[var(--color-border)] py-2.5 text-sm last:border-none sm:flex-row sm:items-center sm:justify-between">
      <span className="text-[var(--color-text-muted)]">{label}</span>
      <span className="min-w-0 break-all font-mono text-[var(--color-text)] sm:text-right">
        {value === undefined || value === "" ? "Not provided by backend" : value}
      </span>
    </div>
  );
}

export function DeveloperPage() {
  const { activeSession } = useChatHistory();
  const { indexType, topK, setIndexType, setTopK, lock } = useDeveloperMode();
  const { data: indexSettings } = useQuery({
    queryKey: ["indexSettings"],
    queryFn: getIndexSettings,
    staleTime: Infinity,
  });
  const lastWithDebug = [...activeSession.messages].reverse().find((m) => m.debug);

  return (
    <div className="mx-auto max-w-2xl px-4 py-6 sm:py-8">
      <div className="flex flex-wrap items-center gap-2">
        <Terminal className="h-5 w-5 text-[var(--color-text-muted)]" />
        <h1 className="text-xl font-semibold text-[var(--color-text)]">RAG Details</h1>
        {USE_MOCK_API && <Badge tone="warning">Mock Data</Badge>}
        <Button
          size="sm"
          variant="ghost"
          className="ml-auto"
          icon={<Lock className="h-3.5 w-3.5" />}
          onClick={lock}
        >
          Lock
        </Button>
      </div>
      <p className="mt-1 text-sm text-[var(--color-text-muted)]">
        Retrieval and generation details for the most recent query in this chat. Useful for the
        term-project demonstration.
      </p>

      <section className="mt-6 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 sm:p-5">
        <div className="flex items-center gap-2">
          <Settings2 className="h-4 w-4 text-[var(--color-accent)]" aria-hidden="true" />
          <h2 className="text-sm font-semibold text-[var(--color-text)]">Retrieval settings</h2>
        </div>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">
          These settings apply to the next <code className="font-mono">/suggest</code> or filter search. Follow-ups reuse the current grounded laptops.
        </p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <label className="space-y-1.5 text-xs font-medium text-[var(--color-text-muted)]">
            FAISS index
            <select
              value={indexType}
              onChange={(event) => setIndexType(event.target.value as ApiIndexType)}
              className="block w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              {(indexSettings?.options ?? []).map((option) => (
                <option key={option.id} value={option.id} disabled={!option.available}>
                  {option.label}{option.id === "ivf_flat" ? " (default)" : ""}
                </option>
              ))}
              {!indexSettings && <option value="ivf_flat">IVF Flat (default)</option>}
            </select>
          </label>
          <label className="space-y-1.5 text-xs font-medium text-[var(--color-text-muted)]">
            Number of laptops (K)
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={1}
                max={20}
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
                className="min-w-0 flex-1 accent-[var(--color-accent)]"
              />
              <input
                type="number"
                min={1}
                max={20}
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
                className="w-16 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-2 text-center text-sm text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                aria-label="Number of laptops to retrieve"
              />
            </div>
          </label>
        </div>
      </section>

      {!lastWithDebug || !lastWithDebug.debug ? (
        <div className="mt-6">
          <EmptyState
            title="No query yet"
            description="Ask the assistant something in the Chat tab to see retrieval and generation details here."
          />
        </div>
      ) : (
        <div className="mt-6 space-y-4">
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-faint)]">
              Query
            </h2>
            <p className="rounded-lg bg-[var(--color-surface-2)] px-3 py-2 text-sm text-[var(--color-text)]">
              {lastWithDebug.debug.query}
            </p>
            {lastWithDebug.debug.filters && Object.keys(lastWithDebug.debug.filters).length > 0 && (
              <pre className="mt-2 overflow-x-auto rounded-lg bg-[var(--color-surface-2)] px-3 py-2 text-xs text-[var(--color-text-muted)]">
                {JSON.stringify(lastWithDebug.debug.filters, null, 2)}
              </pre>
            )}
          </div>

          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
            <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-faint)]">
              Retrieval Pipeline
            </h2>
            <Row label="Embedding Model" value={lastWithDebug.debug.embeddingModel} />
            <Row label="FAISS Index Type" value={lastWithDebug.debug.faissIndexType} />
            <Row label="Top-K" value={lastWithDebug.debug.topK} />
            <Row label="Retrieved IDs" value={lastWithDebug.debug.retrievedIds?.join(", ")} />
          </div>

          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
            <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-faint)]">
              Latency
            </h2>
            <Row
              label="Retrieval Latency"
              value={
                lastWithDebug.debug.retrievalLatencyMs !== undefined
                  ? `${lastWithDebug.debug.retrievalLatencyMs} ms`
                  : undefined
              }
            />
            <Row
              label="Generation Latency"
              value={
                lastWithDebug.debug.generationLatencyMs !== undefined
                  ? `${lastWithDebug.debug.generationLatencyMs} ms`
                  : undefined
              }
            />
            <Row
              label="Total Latency"
              value={
                lastWithDebug.debug.totalLatencyMs !== undefined
                  ? `${lastWithDebug.debug.totalLatencyMs} ms`
                  : undefined
              }
            />
          </div>
        </div>
      )}
    </div>
  );
}
