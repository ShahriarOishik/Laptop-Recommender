import { afterEach, describe, expect, it, vi } from "vitest";
import { EXPLORE_PAGE_SIZE, listLaptops } from "./laptopService";

const responseBody = {
  total: 50,
  limit: 24,
  offset: 24,
  items: [
    { laptop_id: 2, brand: "Zulu", model: "Expensive", price_usd: 2000 },
    { laptop_id: 1, brand: "Alpha", model: "Affordable", price_usd: 500 },
  ],
  facets: { brands: [], gpu_tags: [], operating_systems: [] },
};

describe("listLaptops", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends bounded pagination and sorting to the server", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(responseBody), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await listLaptops({
      page: 2,
      search: "think pad",
      sort: "price-desc",
      filters: { brands: ["Dell"], minRam: 16, minVram: 8 },
    });

    const requestUrl = new URL(fetchMock.mock.calls[0][0], "http://localhost");
    expect(requestUrl.pathname).toBe("/laptops");
    expect(requestUrl.searchParams.get("limit")).toBe("24");
    expect(requestUrl.searchParams.get("offset")).toBe("24");
    expect(requestUrl.searchParams.get("sort")).toBe("price-desc");
    expect(requestUrl.searchParams.get("search")).toBe("think pad");
    expect(requestUrl.searchParams.getAll("brands")).toEqual(["dell"]);
    expect(requestUrl.searchParams.get("min_ram_gb")).toBe("16");
    expect(requestUrl.searchParams.get("min_vram_gb")).toBe("8");
    expect(EXPLORE_PAGE_SIZE).toBe(24);
    expect(result.page).toBe(2);
  });

  it("preserves server order instead of sorting the current page locally", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(responseBody), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      )
    );

    const result = await listLaptops({ sort: "price-asc" });

    expect(result.items.map((laptop) => laptop.id)).toEqual(["2", "1"]);
    expect(result.total).toBe(50);
    expect(result.pageSize).toBe(24);
  });
});
