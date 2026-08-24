import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ErrorBoundary } from "./ErrorBoundary";

function Bomb(): never {
  throw new Error("boom");
}

describe("ErrorBoundary", () => {
  it("renders children normally when nothing throws", () => {
    render(
      <ErrorBoundary>
        <p>All good</p>
      </ErrorBoundary>
    );
    expect(screen.getByText("All good")).toBeInTheDocument();
  });

  it("catches a render error and shows a fallback instead of crashing", () => {
    // React logs the caught error to the console by default — silence it
    // for this test only, the assertion is on the fallback UI, not the log.
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary section="the chat">
        <Bomb />
      </ErrorBoundary>
    );
    expect(screen.getByText(/something went wrong in the chat/i)).toBeInTheDocument();
    consoleSpy.mockRestore();
  });

  it('"Try again" resets the boundary so a subsequent clean render works', async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const user = userEvent.setup();
    let shouldThrow = true;
    function Flaky() {
      if (shouldThrow) throw new Error("boom");
      return <p>Recovered</p>;
    }

    const { rerender } = render(
      <ErrorBoundary>
        <Flaky />
      </ErrorBoundary>
    );
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();

    shouldThrow = false;
    await user.click(screen.getByRole("button", { name: /try again/i }));
    rerender(
      <ErrorBoundary>
        <Flaky />
      </ErrorBoundary>
    );

    expect(screen.getByText("Recovered")).toBeInTheDocument();
    consoleSpy.mockRestore();
  });
});
