import { Badge } from "@/components/common/Badge";

export function LaptopBadge({ category }: { category: string }) {
  return <Badge tone="accent">{category}</Badge>;
}

export function LaptopBadgeList({ categories }: { categories?: string[] }) {
  if (!categories || categories.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {categories.map((c) => (
        <LaptopBadge key={c} category={c} />
      ))}
    </div>
  );
}
