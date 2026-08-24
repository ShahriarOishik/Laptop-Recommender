import { describe, expect, it } from "vitest";
import { formatLaptopName, formatPrice, pickRandom, shuffle, summarizeRequirements, vramToGb } from "./utils";

describe("shuffle", () => {
  it("does not mutate the input array", () => {
    const input = [1, 2, 3, 4, 5];
    const copy = [...input];
    shuffle(input);
    expect(input).toEqual(copy);
  });

  it("preserves all elements (just reorders them)", () => {
    const input = ["a", "b", "c", "d", "e"];
    const result = shuffle(input);
    expect(result).toHaveLength(input.length);
    expect(new Set(result)).toEqual(new Set(input));
  });
});

describe("pickRandom", () => {
  it("returns the requested count when the pool is larger", () => {
    const pool = Array.from({ length: 20 }, (_, i) => i);
    expect(pickRandom(pool, 6)).toHaveLength(6);
  });

  it("clamps to the pool size instead of throwing or padding", () => {
    expect(pickRandom([1, 2, 3], 10)).toHaveLength(3);
  });

  it("only returns items that exist in the source pool", () => {
    const pool = ["a", "b", "c", "d", "e", "f"];
    const picked = pickRandom(pool, 4);
    for (const item of picked) {
      expect(pool).toContain(item);
    }
  });

  it("never repeats an item within one pick", () => {
    const pool = Array.from({ length: 30 }, (_, i) => i);
    const picked = pickRandom(pool, 15);
    expect(new Set(picked).size).toBe(picked.length);
  });
});

describe("formatPrice", () => {
  it("formats a number with a dollar sign and thousands separators", () => {
    expect(formatPrice(1200)).toBe("$1,200");
  });

  it("falls back to a readable label when price is missing", () => {
    expect(formatPrice(undefined)).toBe("Not available");
  });
});

describe("formatLaptopName", () => {
  it("does not repeat a brand already present at the start of the model", () => {
    expect(formatLaptopName("Lenovo", "Lenovo IdeaPad Slim 5")).toBe("Lenovo IdeaPad Slim 5");
  });

  it("matches an existing leading brand case-insensitively", () => {
    expect(formatLaptopName("ASUS", "Asus Vivobook 15")).toBe("Asus Vivobook 15");
  });

  it("adds the brand when the model does not already contain it", () => {
    expect(formatLaptopName("Dell", "XPS 13")).toBe("Dell XPS 13");
  });

  it("does not mistake a partial model prefix for the complete brand", () => {
    expect(formatLaptopName("HP", "HPVictus 15")).toBe("HP HPVictus 15");
  });
});

describe("vramToGb", () => {
  it("reads VRAM expressed in gigabytes", () => {
    expect(vramToGb("NVIDIA RTX 4060 - 8 GB VRAM")).toBe(8);
  });

  it("converts VRAM expressed in megabytes", () => {
    expect(vramToGb("NVIDIA MX150 - 2048 MB VRAM")).toBe(2);
  });

  it("does not treat shared graphics memory as dedicated VRAM", () => {
    expect(vramToGb("Intel Iris Xe - shared memory")).toBe(0);
  });
});

describe("summarizeRequirements", () => {
  it("summarizes active filters as human-readable lines", () => {
    const lines = summarizeRequirements("ignored when filters exist", {
      maxPrice: 1000,
      minRam: 16,
    });
    expect(lines).toEqual(["Budget ≤ $1000", "RAM ≥ 16 GB"]);
  });

  it("falls back to the raw query when no filters are active", () => {
    expect(summarizeRequirements("gaming laptop", {})).toEqual(["gaming laptop"]);
  });
});
