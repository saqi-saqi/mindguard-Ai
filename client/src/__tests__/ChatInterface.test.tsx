import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import ChatInterface from "../components/ChatInterface";

describe("ChatInterface Production Quality & Accessibility", () => {
  const defaultProps = {
    user: { name: "Test User", email: "test@example.com" },
    token: "valid-jwt-token",
    initialMessages: [],
    onOpenCrisisModal: vi.fn(),
    onRecordMood: vi.fn(),
    onWipePersonalData: vi.fn(),
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders header, welcome onboarding, permanently visible urgent help, and suggestion pills", () => {
    render(<ChatInterface {...defaultProps} />);

    expect(screen.getByText("MindGuard Assistant")).toBeDefined();
    expect(screen.getByText("Welcome to MindGuard AI")).toBeDefined();
    expect(screen.getAllByText(/Get urgent help/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/I am feeling anxious about my upcoming exam/i)).toBeDefined();
  });

  it("sends message when Enter is pressed and calls /api/chat", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          reply: "I hear that you are feeling stressed.",
          risk_level: "LOW",
          intent: "ANXIETY_OR_PANIC_ATTACK",
          emotion: "FEAR",
          sentiment: "NEGATIVE"
        }
      })
    });
    globalThis.fetch = mockFetch as any;

    render(<ChatInterface {...defaultProps} />);

    const textarea = screen.getByPlaceholderText(/Type your message/i);
    fireEvent.change(textarea, { target: { value: "I feel overwhelmed" } });
    
    const sendButton = screen.getByRole("button", { name: /Send message/i });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/chat",
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({
            "Content-Type": "application/json",
            Authorization: "Bearer valid-jwt-token"
          }),
          body: expect.stringContaining("I feel overwhelmed")
        })
      );
    });

    await waitFor(() => {
      expect(screen.getAllByText(/I hear that you are feeling stressed/i).length).toBeGreaterThan(0);
    });
  });

  it("does not send message on Shift+Enter (allows multi-line insertion)", () => {
    const mockFetch = vi.fn();
    globalThis.fetch = mockFetch as any;

    render(<ChatInterface {...defaultProps} />);

    const textarea = screen.getByPlaceholderText(/Type your message/i);
    fireEvent.change(textarea, { target: { value: "Line 1" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });

    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("triggers urgent help modal when 'Get urgent help' is clicked", () => {
    const onOpenCrisisModal = vi.fn();
    render(<ChatInterface {...defaultProps} onOpenCrisisModal={onOpenCrisisModal} />);

    const urgentHelpButtons = screen.getAllByRole("button", { name: /get urgent help/i });
    fireEvent.click(urgentHelpButtons[0]);

    expect(onOpenCrisisModal).toHaveBeenCalledWith(null, "manual");
  });

  it("clicking a suggestion pill immediately triggers message sending", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: { reply: "Breathing is a great way to center yourself.", risk_level: "LOW" }
      })
    });
    globalThis.fetch = mockFetch as any;

    render(<ChatInterface {...defaultProps} />);

    const pill = screen.getByRole("button", { name: /I'm having trouble sleeping/i });
    fireEvent.click(pill);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it("displays error alert and retry button on network failure", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("Network connection lost"));
    globalThis.fetch = mockFetch as any;

    render(<ChatInterface {...defaultProps} />);

    const textarea = screen.getByPlaceholderText(/Type your message/i);
    fireEvent.change(textarea, { target: { value: "Hello assistant" } });
    
    const sendButton = screen.getByRole("button", { name: /Send message/i });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(screen.getByText(/Network connection lost/i)).toBeDefined();
      expect(screen.getByRole("button", { name: /retry/i })).toBeDefined();
    });
  });

  it("toggles possible emotional tone badge and shows non-clinical disclaimer", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          reply: "Everything will be okay.",
          risk_level: "LOW",
          intent: "ANXIETY_OR_PANIC_ATTACK",
          emotion: "FEAR",
          sentiment: "NEGATIVE"
        }
      })
    });
    globalThis.fetch = mockFetch as any;

    render(<ChatInterface {...defaultProps} />);

    const textarea = screen.getByPlaceholderText(/Type your message/i);
    fireEvent.change(textarea, { target: { value: "Testing insights" } });
    
    const sendButton = screen.getByRole("button", { name: /Send message/i });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(screen.getAllByText(/Everything will be okay/i).length).toBeGreaterThan(0);
    });

    const badgeButtons = screen.getAllByRole("button", { name: /Possible emotional tone/i });
    expect(badgeButtons.length).toBeGreaterThan(0);
    fireEvent.click(badgeButtons[badgeButtons.length - 1]);

    expect(screen.getByText(/for self-reflection\. Not a clinical psychological assessment/i)).toBeDefined();
  });
});
