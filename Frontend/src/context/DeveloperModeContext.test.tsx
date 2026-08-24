import { useLocation } from "react-router-dom";
import { MemoryRouter } from "react-router-dom";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { DeveloperModeProvider, useDeveloperMode } from "./DeveloperModeContext";

function Probe() {
  const { isUnlocked, indexType, topK, setIndexType, setTopK } = useDeveloperMode();
  const location = useLocation();
  return (
    <div>
      <span>Unlocked: {String(isUnlocked)}</span>
      <span>Index: {indexType}</span>
      <span>Top K: {topK}</span>
      <span>Path: {location.pathname}</span>
      <button onClick={() => setIndexType("hnsw")}>Use HNSW</button>
      <button onClick={() => setTopK(12)}>Use 12 results</button>
    </div>
  );
}

describe("DeveloperModeProvider", () => {
  beforeEach(() => sessionStorage.clear());

  it("toggles off and resets settings when Ctrl+Shift+D is pressed again", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <DeveloperModeProvider>
          <Probe />
        </DeveloperModeProvider>
      </MemoryRouter>
    );

    fireEvent.keyDown(window, { key: "d", ctrlKey: true, shiftKey: true });
    expect(screen.getByText("Unlocked: true")).toBeInTheDocument();
    expect(screen.getByText("Path: /developer")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Use HNSW" }));
    await user.click(screen.getByRole("button", { name: "Use 12 results" }));
    expect(screen.getByText("Index: hnsw")).toBeInTheDocument();
    expect(screen.getByText("Top K: 12")).toBeInTheDocument();

    act(() => fireEvent.keyDown(window, { key: "d", ctrlKey: true, shiftKey: true }));

    expect(screen.getByText("Unlocked: false")).toBeInTheDocument();
    expect(screen.getByText("Index: ivf_flat")).toBeInTheDocument();
    expect(screen.getByText("Top K: 5")).toBeInTheDocument();
    expect(screen.getByText("Path: /")).toBeInTheDocument();
    expect(sessionStorage.getItem("lapwise-developer-unlocked")).toBeNull();
  });
});
