import { describe, expect, it } from "vitest";
import { visiblePageNumbers } from "./explorePagination";

describe("visiblePageNumbers", () => {
  it("keeps a bounded window around the current page", () => {
    expect(visiblePageNumbers(1, 20)).toEqual([1, 2, 3, 4, 5]);
    expect(visiblePageNumbers(10, 20)).toEqual([8, 9, 10, 11, 12]);
    expect(visiblePageNumbers(20, 20)).toEqual([16, 17, 18, 19, 20]);
  });

  it("lists every page when the result has fewer than five pages", () => {
    expect(visiblePageNumbers(2, 3)).toEqual([1, 2, 3]);
  });
});
