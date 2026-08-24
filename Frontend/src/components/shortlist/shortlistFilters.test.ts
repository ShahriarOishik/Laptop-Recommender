import { describe, expect, it } from "vitest";
import type { Laptop } from "@/types/laptop";
import { capacityToGb, countShortlistFilters, filterShortlist } from "./shortlistFilters";

const laptops: Laptop[] = [
  {
    id: "1",
    name: "Atlas Pro",
    brand: "Acme",
    price: 1200,
    cpu: "Intel Core Ultra 7",
    gpu: "NVIDIA RTX 4060",
    ram: "16 GB DDR5",
    storage: "1 TB SSD",
    operatingSystem: "Windows 11",
  },
  {
    id: "2",
    name: "Feather Air",
    brand: "Pear",
    price: 900,
    cpu: "Pear M3",
    gpu: "Integrated",
    ram: "8GB unified",
    storage: "512 GB SSD",
    operatingSystem: "Pear OS",
  },
];

describe("capacityToGb", () => {
  it("normalizes GB and TB specification strings", () => {
    expect(capacityToGb("16 GB DDR5")).toBe(16);
    expect(capacityToGb("1.5 TB NVMe SSD")).toBe(1536);
    expect(capacityToGb(undefined)).toBeUndefined();
  });
});

describe("filterShortlist", () => {
  it("searches laptop name, brand, CPU, and GPU case-insensitively", () => {
    expect(filterShortlist(laptops, "rtx 4060", {})).toEqual([laptops[0]]);
    expect(filterShortlist(laptops, "PEAR", {})).toEqual([laptops[1]]);
  });

  it("combines brand, price, capacity, and OS filters", () => {
    expect(
      filterShortlist(laptops, "", {
        brand: "Acme",
        minPrice: 1000,
        maxPrice: 1300,
        minRam: 16,
        minStorage: 1024,
        operatingSystem: "Windows 11",
      })
    ).toEqual([laptops[0]]);
  });

  it("excludes unknown specifications when a minimum is active", () => {
    expect(filterShortlist([{ id: "3", name: "Unknown" }], "", { minRam: 8 })).toEqual([]);
  });
});

describe("countShortlistFilters", () => {
  it("counts each active control", () => {
    expect(countShortlistFilters({ brand: "Acme", minPrice: 500, minRam: 16 })).toBe(3);
  });
});
