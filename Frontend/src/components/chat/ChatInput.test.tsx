import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatInput } from "./ChatInput";

describe("ChatInput", () => {
  it("shows the slash-command menu while typing a command name", async () => {
    const user = userEvent.setup();
    render(<ChatInput onSubmit={vi.fn()} />);
    const textarea = screen.getByRole("combobox");

    await user.type(textarea, "/sug");

    expect(screen.getByRole("listbox", { name: /slash commands/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /suggest/i })).toBeInTheDocument();
  });

  it("closes the menu once a space follows the command", async () => {
    const user = userEvent.setup();
    render(<ChatInput onSubmit={vi.fn()} />);
    const textarea = screen.getByRole("combobox");

    await user.type(textarea, "/suggest ");

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("submits a plain message as chat, not a command", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ChatInput onSubmit={onSubmit} />);
    const textarea = screen.getByRole("combobox");

    await user.type(textarea, "why is the first one good{Enter}");

    expect(onSubmit).toHaveBeenCalledWith("why is the first one good", { forceRetrieval: false });
  });

  it("submits /suggest text with forceRetrieval: true and strips the command prefix", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ChatInput onSubmit={onSubmit} />);
    const textarea = screen.getByRole("combobox");

    await user.type(textarea, "/suggest gaming laptop{Enter}");

    expect(onSubmit).toHaveBeenCalledWith("gaming laptop", { forceRetrieval: true });
  });

  it("clears the input after a successful submit", async () => {
    const user = userEvent.setup();
    render(<ChatInput onSubmit={vi.fn()} />);
    const textarea = screen.getByRole("combobox") as HTMLTextAreaElement;

    await user.type(textarea, "hello{Enter}");

    expect(textarea.value).toBe("");
  });

  it("disables the send button for a bare /suggest with no active filters", async () => {
    const user = userEvent.setup();
    render(<ChatInput onSubmit={vi.fn()} activeFilterCount={0} />);
    const textarea = screen.getByRole("combobox");

    await user.type(textarea, "/suggest ");

    expect(screen.getByRole("button", { name: /send message/i })).toBeDisabled();
  });

  it("enables sending a bare /suggest when filters are active (filter-only search)", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ChatInput onSubmit={onSubmit} activeFilterCount={2} />);
    const textarea = screen.getByRole("combobox");

    await user.type(textarea, "/suggest ");
    expect(screen.getByRole("button", { name: /send message/i })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: /send message/i }));
    expect(onSubmit).toHaveBeenCalledWith("", { forceRetrieval: true });
  });

  it("does not submit on Enter while disabled (a request is already in flight)", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ChatInput onSubmit={onSubmit} disabled />);
    const textarea = screen.getByRole("combobox");

    expect(textarea).toBeDisabled();
    await user.type(textarea, "hello{Enter}", { skipClick: true });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("Escape dismisses the command menu without submitting", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ChatInput onSubmit={onSubmit} />);
    const textarea = screen.getByRole("combobox");

    await user.type(textarea, "/sug");
    expect(screen.getByRole("listbox")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
