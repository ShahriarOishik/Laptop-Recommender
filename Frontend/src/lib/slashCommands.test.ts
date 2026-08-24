import { describe, expect, it } from "vitest";
import { isTypingCommandName, matchingCommands, parseSlashCommand, SLASH_COMMANDS } from "./slashCommands";

describe("parseSlashCommand", () => {
  it("treats plain text as chat with no command", () => {
    expect(parseSlashCommand("hello world")).toEqual({ text: "hello world" });
  });

  it("recognizes /suggest and strips it from the text", () => {
    expect(parseSlashCommand("/suggest gaming laptop")).toEqual({
      command: "suggest",
      text: "gaming laptop",
    });
  });

  it("returns empty text for a bare command with nothing after it", () => {
    expect(parseSlashCommand("/suggest")).toEqual({ command: "suggest", text: "" });
    expect(parseSlashCommand("/suggest ")).toEqual({ command: "suggest", text: "" });
  });

  it("falls back to plain text for an unknown command", () => {
    expect(parseSlashCommand("/frobnicate something")).toEqual({ text: "/frobnicate something" });
  });

  it("trims surrounding whitespace and collapses interior spacing around the command", () => {
    expect(parseSlashCommand("   /suggest   under $900  ")).toEqual({
      command: "suggest",
      text: "under $900",
    });
  });

  it("is case-insensitive on the command name", () => {
    expect(parseSlashCommand("/SUGGEST gaming laptop").command).toBe("suggest");
  });
});

describe("isTypingCommandName", () => {
  it("is true while a leading slash has no trailing space yet", () => {
    expect(isTypingCommandName("/")).toBe(true);
    expect(isTypingCommandName("/s")).toBe(true);
    expect(isTypingCommandName("/suggest")).toBe(true);
  });

  it("is false once a space follows the command (now typing the query)", () => {
    expect(isTypingCommandName("/suggest ")).toBe(false);
    expect(isTypingCommandName("/suggest gaming laptop")).toBe(false);
  });

  it("is false for plain text with no leading slash", () => {
    expect(isTypingCommandName("hello")).toBe(false);
    expect(isTypingCommandName("")).toBe(false);
  });
});

describe("matchingCommands", () => {
  it("returns all commands for a bare slash", () => {
    expect(matchingCommands("/")).toEqual(SLASH_COMMANDS);
  });

  it("filters by the typed prefix, case-insensitively", () => {
    expect(matchingCommands("/sug").map((c) => c.name)).toEqual(["suggest"]);
    expect(matchingCommands("/SUG").map((c) => c.name)).toEqual(["suggest"]);
  });

  it("returns nothing for a prefix no command matches", () => {
    expect(matchingCommands("/zzz")).toEqual([]);
  });
});
