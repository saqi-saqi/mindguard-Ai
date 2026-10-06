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

  it("persists emergency banner across follow-up non-crisis messages in active session", async () => {
    let callCount = 0;
    const mockFetch = vi.fn().mockImplementation(async () => {
      callCount++;
      if (callCount === 1) {
        // Turn 1: HIGH_CRISIS response
        return {
          ok: true,
          json: async () => ({
            success: true,
            data: {
              reply: "Crisis safety protocol",
              risk_level: "HIGH_CRISIS",
              session_id: "ses-12345",
              requires_immediate_action: true
            }
          })
        };
      } else {
        // Turn 2: Follow up
        return {
          ok: true,
          json: async () => ({
            success: true,
            data: {
              reply: "I hear you, make sure you are safe.",
              risk_level: "ELEVATED_DISTRESS",
              session_id: "ses-12345",
              requires_immediate_action: false
            }
          })
        };
      }
    });
    globalThis.fetch = mockFetch as any;
    const onOpenCrisisModal = vi.fn();

    render(<ChatInterface {...defaultProps} onOpenCrisisModal={onOpenCrisisModal} />);

    const textarea = screen.getByPlaceholderText(/Type your message/i);
    const sendButton = screen.getByRole("button", { name: /Send message/i });

    // Send Turn 1
    fireEvent.change(textarea, { target: { value: "I want to die" } });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(onOpenCrisisModal).toHaveBeenCalledWith(undefined, "detected");
      expect(screen.getByText(/If you may be in physical danger/i)).toBeDefined();
    });

    // Send Turn 2: casual message
    fireEvent.change(textarea, { target: { value: "tell me a joke" } });
    fireEvent.click(sendButton);

    await waitFor(() => {
      // Banner must STILL be visible
      expect(screen.getByText(/If you may be in physical danger/i)).toBeDefined();
      expect(screen.getByText("I'm safe now")).toBeDefined();
    });

    // Click "I'm safe now" to resolve safety flow
    const safeButton = screen.getByText("I'm safe now");
    fireEvent.click(safeButton);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/chat/session/ses-12345/safety-clear",
        expect.objectContaining({
          method: "POST"
        })
      );
    });
  });

  it("threat to others triggers CrisisModal, styles emergency protocol, and never displays 'Possible emotional tone'", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          reply: "Immediate safety support needed — move away from the person and any weapon or harmful object, and contact emergency services now.",
          risk_level: "HARM_TO_OTHERS_RISK",
          classification: "HARM_TO_OTHERS_RISK",
          intent: "SAFETY PROTOCOL - HARM_TO_OTHERS_RISK",
          emotion: "ACUTE_RISK",
          sentiment: "NEGATIVE",
          requires_immediate_action: true,
          emergency_resources: [
            { organization: "Police", contact_info: "15" },
            { organization: "Rescue", contact_info: "1122" },
            { organization: "Edhi", contact_info: "115" },
            { organization: "Umang", contact_info: "0311-7786264" }
          ]
        }
      })
    });
    globalThis.fetch = mockFetch as any;
    const onOpenCrisisModal = vi.fn();

    render(<ChatInterface {...defaultProps} onOpenCrisisModal={onOpenCrisisModal} />);

    const textarea = screen.getByPlaceholderText(/Type your message/i);
    const sendButton = screen.getByRole("button", { name: /Send message/i });

    fireEvent.change(textarea, { target: { value: "I'm gonna kill my neighbour" } });
    fireEvent.click(sendButton);

    await waitFor(() => {
      // Must open CrisisModal immediately
      expect(onOpenCrisisModal).toHaveBeenCalledWith(expect.anything(), "detected");
      // Must render Emergency Safety Protocol badge
      expect(screen.getByText(/🚨 Emergency Safety Protocol Active/i)).toBeDefined();
    });

    // CRITICAL: Must NEVER label HARM_TO_OTHERS_RISK or COMBINED_HIGH_CRISIS as "Possible emotional tone"
    expect(screen.queryByText(/Possible emotional tone/i)).toBeNull();
  });

  it("third-party report renders distinct panel, does not open CrisisModal, and does not label as distressed", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          reply: "It sounds like you are carrying concern for someone who may be in danger.",
          risk_level: "THIRD_PARTY_REPORT",
          classification: "THIRD_PARTY_REPORT",
          intent: "THIRD PARTY SAFETY REPORT",
          emotion: "CONCERN",
          sentiment: "NEUTRAL",
          requires_immediate_action: false,
          emergency_resources: [
            { organization: "Police", contact_info: "15" }
          ]
        }
      })
    });
    globalThis.fetch = mockFetch as any;
    const onOpenCrisisModal = vi.fn();

    render(<ChatInterface {...defaultProps} onOpenCrisisModal={onOpenCrisisModal} />);

    const textarea = screen.getByPlaceholderText(/Type your message/i);
    const sendButton = screen.getByRole("button", { name: /Send message/i });

    fireEvent.change(textarea, { target: { value: "my friend keeps talking about killing his ex" } });
    fireEvent.click(sendButton);

    await waitFor(() => {
      // Must NOT open CrisisModal (user isn't the one at risk)
      expect(onOpenCrisisModal).not.toHaveBeenCalled();
      // Must render distinct third-party panel
      expect(screen.getByText(/Third-Party Safety & Intervention Guidance/i)).toBeDefined();
      expect(screen.getByText(/🛡️ Third-Party Safety Guidance/i)).toBeDefined();
      // Must include direct emergency contact links in the third-party panel
      expect(screen.getByText(/Call 15 \(Police Emergency\)/i)).toBeDefined();
      expect(screen.getByText(/Call 1122 \(Pakistan Rescue\)/i)).toBeDefined();
      expect(screen.getByText(/Call 115 \(Edhi Ambulance\)/i)).toBeDefined();
    });

    // Must NOT label as mere "Possible emotional tone · Distressed"
    expect(screen.queryByText(/Possible emotional tone · Distressed/i)).toBeNull();
  });

  it("disables composer input and submit button while isCrisisModalOpen is true", () => {
    render(<ChatInterface {...defaultProps} isCrisisModalOpen={true} />);

    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    expect(textarea.disabled).toBe(true);

    const sendButton = screen.getByRole("button", { name: /Send message/i }) as HTMLButtonElement;
    expect(sendButton.disabled).toBe(true);
  });
});

