import { X } from "lucide-react";
import type { Laptop } from "@/types/laptop";
import { formatPrice, formatSpec } from "@/lib/utils";
import { LaptopBadgeList } from "@/components/laptop/LaptopBadge";

const ROWS: { label: string; get: (l: Laptop) => string }[] = [
  { label: "Price", get: (l) => formatPrice(l.price) },
  { label: "CPU", get: (l) => formatSpec(l.cpu) },
  { label: "RAM", get: (l) => formatSpec(l.ram) },
  { label: "Storage", get: (l) => formatSpec(l.storage) },
  { label: "GPU", get: (l) => formatSpec(l.gpu) },
  { label: "Display", get: (l) => formatSpec(l.display) },
  { label: "Battery", get: (l) => formatSpec(l.battery) },
  { label: "Weight", get: (l) => formatSpec(l.weight) },
  { label: "Operating System", get: (l) => formatSpec(l.operatingSystem) },
];

export function ComparisonTable({
  laptops,
  onRemove,
}: {
  laptops: Laptop[];
  onRemove: (id: string) => void;
}) {
  return (
    <div className="overflow-x-auto scrollbar-thin rounded-2xl border border-[var(--color-border)]">
      <table className="w-full min-w-[560px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface-2)]">
            <th className="sticky left-0 bg-[var(--color-surface-2)] px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[var(--color-text-faint)]">
              Spec
            </th>
            {laptops.map((laptop) => (
              <th key={laptop.id} className="min-w-[180px] px-4 py-3 text-left align-top">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-semibold text-[var(--color-text)]">{laptop.name}</p>
                    <div className="mt-1">
                      <LaptopBadgeList categories={laptop.categories?.slice(0, 2)} />
                    </div>
                  </div>
                  <button
                    onClick={() => onRemove(laptop.id)}
                    aria-label={`Remove ${laptop.name} from comparison`}
                    className="rounded-lg p-1 text-[var(--color-text-faint)] hover:bg-[var(--color-surface)] hover:text-[var(--color-danger)]"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row, idx) => (
            <tr
              key={row.label}
              className={idx % 2 === 0 ? "bg-[var(--color-surface)]" : "bg-[var(--color-surface-2)]/40"}
            >
              <td className="sticky left-0 bg-inherit px-4 py-2.5 text-xs font-medium text-[var(--color-text-muted)]">
                {row.label}
              </td>
              {laptops.map((laptop) => (
                <td key={laptop.id} className="px-4 py-2.5 text-[var(--color-text)]">
                  {row.get(laptop)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
