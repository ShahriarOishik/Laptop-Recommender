import { Battery, Cpu, HardDrive, MemoryStick, Monitor, MonitorCheck } from "lucide-react";
import type { Laptop } from "@/types/laptop";
import { formatSpec } from "@/lib/utils";

const specRows = (laptop: Laptop) => [
  { label: "CPU", value: laptop.cpu, icon: Cpu },
  { label: "RAM", value: laptop.ram, icon: MemoryStick },
  { label: "Storage", value: laptop.storage, icon: HardDrive },
  { label: "GPU", value: laptop.gpu, icon: MonitorCheck },
  { label: "Display", value: laptop.display, icon: Monitor },
  { label: "Battery", value: laptop.battery, icon: Battery },
];

export function LaptopSpecs({ laptop, compact }: { laptop: Laptop; compact?: boolean }) {
  return (
    <dl className={compact ? "grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3" : "grid grid-cols-2 gap-x-4 gap-y-2.5"}>
      {specRows(laptop).map(({ label, value, icon: Icon }) => (
        <div key={label} className="flex items-start gap-1.5">
          <Icon className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-[var(--color-text-faint)]" />
          <div className="min-w-0">
            <dt className="text-[11px] uppercase tracking-wide text-[var(--color-text-faint)]">{label}</dt>
            <dd
              className="truncate text-sm text-[var(--color-text)]"
              title={value}
            >
              {formatSpec(value)}
            </dd>
          </div>
        </div>
      ))}
    </dl>
  );
}
