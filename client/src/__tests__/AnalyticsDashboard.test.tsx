import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import AnalyticsDashboard from "../components/AnalyticsDashboard";
import type { MoodLog } from "../components/types";

describe("AnalyticsDashboard Accessibility & Quality", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: { mood_logs: [], message_count: 0, session_count: 0 }
      })
    }) as any;
  });

  it("renders guided onboarding empty state when no logs exist", async () => {
    await act(async () => {
      render(<AnalyticsDashboard moodLogs={[]} token="valid-token" />);
    });

    expect(screen.getByText(/Start with one honest check-in/i)).toBeDefined();
    expect(screen.getByText(/After three check-ins, this page can begin describing your recent pattern/i)).toBeDefined();
    expect(screen.getByRole("button", { name: /Log your first mood check-in/i })).toBeDefined();
  });

  it("provides accessible slider with keyboard arrows support and ARIA attributes", async () => {
    await act(async () => {
      render(<AnalyticsDashboard moodLogs={[]} token="valid-token" />);
    });

    const slider = screen.getByLabelText(/How are you feeling right now/i);
    expect(slider.getAttribute("aria-valuemin")).toBe("1");
    expect(slider.getAttribute("aria-valuemax")).toBe("10");
    expect(slider.getAttribute("aria-valuenow")).toBe("5");

    // Keyboard increment
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(slider.getAttribute("aria-valuenow")).toBe("6");

    // Keyboard decrement
    fireEvent.keyDown(slider, { key: "ArrowLeft" });
    expect(slider.getAttribute("aria-valuenow")).toBe("5");
  });

  it("toggles activity context tag chips", async () => {
    await act(async () => {
      render(<AnalyticsDashboard moodLogs={[]} token="valid-token" />);
    });

    const examTag = screen.getByRole("button", { name: /#Exam/i });
    expect(examTag.getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(examTag);
    expect(examTag.getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(examTag);
    expect(examTag.getAttribute("aria-pressed")).toBe("false");
  });

  it("submits mood log and displays save confirmation feedback", async () => {
    const onMoodCreated = vi.fn();
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          mood_log: { id: "101", score: 8, tags: ["Exercise"], notes: "Went for a run", created_at: new Date().toISOString() }
        }
      })
    });
    globalThis.fetch = mockFetch as any;

    await act(async () => {
      render(<AnalyticsDashboard moodLogs={[]} token="valid-token" onMoodCreated={onMoodCreated} />);
    });

    const exerciseTag = screen.getByRole("button", { name: /#Exercise/i });
    fireEvent.click(exerciseTag);

    const submitBtn = screen.getByRole("button", { name: /Save check-in/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/moods",
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({
            "Content-Type": "application/json",
            Authorization: "Bearer valid-token"
          }),
          body: expect.stringContaining("Exercise")
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByText(/Mood entry saved successfully/i)).toBeDefined();
      expect(onMoodCreated).toHaveBeenCalled();
    });
  });

  it("turns enough check-ins into a cautious reflection and context observation", async () => {
    const sampleLogs: MoodLog[] = [
      { id: "1", score: 2, tags: ["Exam"], notes: "Stressed", created_at: new Date().toISOString() },
      { id: "2", score: 3, tags: ["Exam"], notes: "Hard day", created_at: new Date().toISOString() },
      { id: "3", score: 6, tags: ["Sleep"], notes: "Okay", created_at: new Date().toISOString() },
      { id: "4", score: 7, tags: ["Family"], notes: "Good", created_at: new Date().toISOString() },
      { id: "5", score: 8, tags: ["Exercise"], notes: "Great", created_at: new Date().toISOString() },
    ];

    await act(async () => {
      render(<AnalyticsDashboard moodLogs={sampleLogs} />);
    });

    expect(screen.getByText(/Your recent check-in story/i)).toBeDefined();
    expect(screen.getByText(/appeared in 2 check-ins; those entries averaged 2.5/i)).toBeDefined();
    expect(screen.getByText(/A change is a prompt to reflect, not proof of a cause/i)).toBeDefined();
  });

  it("shows supportive guidance and talk it through button when score is low", async () => {
    const onStartChat = vi.fn();
    await act(async () => {
      render(<AnalyticsDashboard moodLogs={[]} token="valid-token" onStartChat={onStartChat} />);
    });

    const slider = screen.getByLabelText(/How are you feeling right now/i);
    // Lower score to 2
    fireEvent.change(slider, { target: { value: "2" } });

    expect(screen.getByText(/It takes honesty to notice when things feel heavy/i)).toBeDefined();
    const talkThroughBtn = screen.getByRole("button", { name: /Would you like to talk it through in chat\?/i });
    expect(talkThroughBtn).toBeDefined();

    fireEvent.click(talkThroughBtn);
    expect(onStartChat).toHaveBeenCalledTimes(1);
  });

  it("adds custom tag and allows toggling it as a chip", async () => {
    await act(async () => {
      render(<AnalyticsDashboard moodLogs={[]} token="valid-token" />);
    });

    const customTagInput = screen.getByLabelText(/Add custom tag/i);
    fireEvent.change(customTagInput, { target: { value: "Midterms" } });
    fireEvent.keyDown(customTagInput, { key: "Enter" });

    const midtermsChip = screen.getByRole("button", { name: /#Midterms/i });
    expect(midtermsChip).toBeDefined();
    expect(midtermsChip.getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(midtermsChip);
    expect(midtermsChip.getAttribute("aria-pressed")).toBe("false");
  });

  describe("Guest-Mode Auth Gate on Mood & Analytics", () => {
    it("intercepts Save check-in when guest user: opens modal and does not fire API call", async () => {
      const mockFetch = vi.fn();
      globalThis.fetch = mockFetch as any;
      const onMoodCreated = vi.fn();
      const onNavigateToAuth = vi.fn();

      await act(async () => {
        render(
          <AnalyticsDashboard
            moodLogs={[]}
            token=""
            user={null}
            onMoodCreated={onMoodCreated}
            onNavigateToAuth={onNavigateToAuth}
          />
        );
      });

      // Guest clicks Save check-in
      const saveBtn = screen.getByRole("button", { name: /Save check-in/i });
      fireEvent.click(saveBtn);

      // Verify AuthGateModal opens
      expect(screen.getByRole("dialog")).toBeDefined();
      expect(screen.getByText(/Sign In to Save Mood Check-ins/i)).toBeDefined();
      expect(screen.getByRole("button", { name: /^Log In$/i })).toBeDefined();
      expect(screen.getByRole("button", { name: /^Register$/i })).toBeDefined();

      // Original action must NOT fire
      expect(mockFetch).not.toHaveBeenCalled();
      expect(onMoodCreated).not.toHaveBeenCalled();
    });

    it("intercepts Clear Mood History when guest user: opens modal and does not execute clear", async () => {
      const onClearLogs = vi.fn();
      const onNavigateToAuth = vi.fn();
      const sampleLogs: MoodLog[] = [
        { id: "1", score: 7, tags: ["Exercise"], notes: "Good run", created_at: new Date().toISOString() }
      ];

      await act(async () => {
        render(
          <AnalyticsDashboard
            moodLogs={sampleLogs}
            token=""
            user={null}
            onClearLogs={onClearLogs}
            onNavigateToAuth={onNavigateToAuth}
          />
        );
      });

      const clearBtn = screen.getByRole("button", { name: /Clear Mood History/i });
      fireEvent.click(clearBtn);

      // Verify modal opens and onClearLogs did not fire
      expect(screen.getByRole("dialog")).toBeDefined();
      expect(onClearLogs).not.toHaveBeenCalled();
    });

    it("allows routing to Log In and Register from modal and dismissal to stay on page", async () => {
      const onNavigateToAuth = vi.fn();

      await act(async () => {
        render(
          <AnalyticsDashboard
            moodLogs={[]}
            token=""
            user={null}
            onNavigateToAuth={onNavigateToAuth}
          />
        );
      });

      const saveBtn = screen.getByRole("button", { name: /Save check-in/i });
      fireEvent.click(saveBtn);

      // Click Log In
      const loginBtn = screen.getByRole("button", { name: /^Log In$/i });
      fireEvent.click(loginBtn);
      expect(onNavigateToAuth).toHaveBeenCalledWith("login");
      expect(screen.queryByRole("dialog")).toBeNull();

      // Re-trigger and click Register
      fireEvent.click(saveBtn);
      const registerBtn = screen.getByRole("button", { name: /^Register$/i });
      fireEvent.click(registerBtn);
      expect(onNavigateToAuth).toHaveBeenCalledWith("register");
      expect(screen.queryByRole("dialog")).toBeNull();

      // Re-trigger and dismiss
      fireEvent.click(saveBtn);
      const dismissBtn = screen.getByRole("button", { name: /Stay on page \(Dismiss\)/i });
      fireEvent.click(dismissBtn);
      expect(screen.queryByRole("dialog")).toBeNull();
    });

    it("allows authenticated user to click Clear Mood History normally without auth modal", async () => {
      const onClearLogs = vi.fn();
      const sampleLogs: MoodLog[] = [
        { id: "1", score: 7, tags: ["Exercise"], notes: "Good run", created_at: new Date().toISOString() }
      ];
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          success: true,
          data: { mood_logs: sampleLogs }
        })
      }) as any;

      await act(async () => {
        render(
          <AnalyticsDashboard
            moodLogs={sampleLogs}
            token="valid-token"
            onClearLogs={onClearLogs}
          />
        );
      });

      const clearBtn = screen.getByRole("button", { name: /Clear Mood History/i });
      fireEvent.click(clearBtn);

      expect(onClearLogs).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole("dialog")).toBeNull();
    });
  });
});
