export interface SlashCommand {
  name: string;
  usage: string;
  description: string;
}

/** The only command that changes request behavior today: it forces a fresh
 * FAISS retrieval. Add future commands here — ChatInput's menu and
 * parseSlashCommand both read from this single list. */
export const SLASH_COMMANDS: SlashCommand[] = [
  {
    name: "suggest",
    usage: "/suggest <what you're looking for>",
    description: "Search the laptop dataset and get new top-5 recommendations",
  },
];

export interface ParsedInput {
  /** Recognized command name (without the slash), or undefined for plain chat. */
  command?: string;
  /** The message text with the "/command" prefix stripped and trimmed. */
  text: string;
}

const COMMAND_PATTERN = /^\/(\w+)\b\s*(.*)$/s;

export function parseSlashCommand(raw: string): ParsedInput {
  const trimmed = raw.trim();
  const match = COMMAND_PATTERN.exec(trimmed);
  if (!match) return { text: trimmed };
  const [, name, rest] = match;
  const known = SLASH_COMMANDS.find((c) => c.name === name.toLowerCase());
  if (!known) return { text: trimmed };
  return { command: known.name, text: rest.trim() };
}

/** True while the caret is inside/after a leading "/word" with no space yet
 * — i.e. the user is actively typing a command name and the menu should
 * offer to complete it. */
export function isTypingCommandName(raw: string): boolean {
  return /^\/[a-zA-Z]*$/.test(raw);
}

export function matchingCommands(raw: string): SlashCommand[] {
  const query = raw.trim().slice(1).toLowerCase();
  return SLASH_COMMANDS.filter((c) => c.name.startsWith(query));
}
