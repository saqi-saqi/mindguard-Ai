import { render, screen, fireEvent, waitFor } from "@testing-library/react";
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

  it("renders guided onboarding empty state when no logs exist", () => {
    render(<AnalyticsDashboard moodLogs={[]} token="valid-token" />);

    expect(screen.getByText(/Start Tracking Your Emotional Well-being/i)).toBeDefined();
    expect(screen.getByText(/Your mood history and reflection trends will appear here/i)).toBeDefined();
    expect(screen.getByRole("button", { name: /Log your first mood check-in/i })).toBeDefined();
  });

  it("provides accessible slider with keyboard arrows support and ARIA attributes", () => {
    render(<AnalyticsDashboard moodLogs={[]} token="valid-token" />);

    const slider = screen.getByLabelText(/Select Mood Rating/i);
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

  it("toggles activity context tag chips", () => {
    render(<AnalyticsDashboard moodLogs={[]} token="valid-token" />);

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

    render(<AnalyticsDashboard moodLogs={[]} token="valid-token" onMoodCreated={onMoodCreated} />);

    const exerciseTag = screen.getByRole("button", { name: /#Exercise/i });
    fireEvent.click(exerciseTag);

    const submitBtn = screen.getByRole("button", { name: /Save Mood Entry/i });
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

  it("displays cautious, non-causal reflection insights when 5+ logs exist", () => {
    const sampleLogs: MoodLog[] = [
      { id: "1", score: 2, tags: ["Exam"], notes: "Stressed", created_at: new Date().toISOString() },
      { id: "2", score: 3, tags: ["Exam"], notes: "Hard day", created_at: new Date().toISOString() },
      { id: "3", score: 6, tags: ["Sleep"], notes: "Okay", created_at: new Date().toISOString() },
      { id: "4", score: 7, tags: ["Family"], notes: "Good", created_at: new Date().toISOString() },
      { id: "5", score: 8, tags: ["Exercise"], notes: "Great", created_at: new Date().toISOString() },
    ];

    render(<AnalyticsDashboard moodLogs={sampleLogs} token="valid-token" />);

    expect(screen.getByText(/Self-Reflection Pattern/i)).toBeDefined();
    expect(screen.getByText(/Topic "exam" appeared frequently alongside lower mood scores/i)).toBeDefined();
    expect(screen.getByText(/Note: Patterns describe correlation in your entries, not medical causation or diagnosis/i)).toBeDefined();
  });
});
