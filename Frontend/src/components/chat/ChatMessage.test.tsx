import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ChatMessage as ChatMessageType } from "@/types/chat";
import { ChatMessage } from "./ChatMessage";

vi.mock("@/components/laptop/LaptopRecommendationCard", () => ({
  LaptopRecommendationCard: ({ recommendation }: { recommendation: { laptop: { name: string } } }) => (
    <article>{recommendation.laptop.name}</article>
  ),
}));

const recommendation = {
  laptop: { id: "1", name: "Test Laptop", price: 799 },
  reasoning: "Matches the request",
};

function assistantMessage(patch: Partial<ChatMessageType> = {}): ChatMessageType {
  return {
    id: "assistant-1",
    role: "assistant",
    createdAt: Date.now(),
    ...patch,
  };
}

describe("ChatMessage", () => {
  it("shows only recommendation cards for /suggest responses", () => {
    render(
      <ChatMessage
        message={assistantMessage({
          text: "Here are the laptops I recommend.",
          recommendations: [recommendation],
          requestForceRetrieval: true,
          isAnswerPending: true,
          hasExactMatches: false,
          message: "The budget was relaxed.",
          relaxedFilters: ["price_range"],
        })}
        onFollowUp={() => {}}
      />
    );

    expect(screen.getByText("Test Laptop")).toBeInTheDocument();
    expect(screen.queryByText("Here are the laptops I recommend.")).not.toBeInTheDocument();
    expect(screen.queryByText("Writing an explanation…")).not.toBeInTheDocument();
    expect(screen.queryByText("The budget was relaxed.")).not.toBeInTheDocument();
    expect(screen.queryByText("No exact matches found")).not.toBeInTheDocument();
    expect(screen.queryByText("Follow-up questions")).not.toBeInTheDocument();
  });

  it("continues to show text for ordinary chat responses", () => {
    render(<ChatMessage message={assistantMessage({ text: "A normal chat answer." })} />);

    expect(screen.getByText("A normal chat answer.")).toBeInTheDocument();
  });
});
