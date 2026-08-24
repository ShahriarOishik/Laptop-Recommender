import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FilterPanel, countActiveFilters } from "./FilterPanel";

vi.mock("@/services/laptopService", () => ({
  getAllBrands: vi.fn().mockResolvedValue([]),
}));

describe("FilterPanel VRAM filter", () => {
  it("shows minimum VRAM options and updates the selected value", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <FilterPanel filters={{}} onChange={onChange} />
      </QueryClientProvider>
    );

    const vramOptions = screen.getByText("Minimum VRAM").nextElementSibling as HTMLElement;
    expect(screen.queryByRole("button", { name: "NVIDIA" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Dedicated GPU" })).not.toBeInTheDocument();
    expect(within(vramOptions).getByRole("button", { name: "2 GB+" })).toBeInTheDocument();
    expect(within(vramOptions).getByRole("button", { name: "16 GB+" })).toBeInTheDocument();

    await user.click(within(vramOptions).getByRole("button", { name: "8 GB+" }));
    expect(onChange).toHaveBeenCalledWith({ minVram: 8 });
  });

  it("counts VRAM as an active filter", () => {
    expect(countActiveFilters({ minVram: 8 })).toBe(1);
  });
});
