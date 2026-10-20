import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import AdminSafetyLogs from "../components/AdminSafetyLogs";
import type { MindUser } from "../components/types";

describe("AdminSafetyLogs UI Component", () => {
  const adminUser: MindUser = {
    id: "usr-admin1",
    name: "Dr. Admin",
    email: "admin@mindguard.ai",
    role: "admin",
  };

  const regularUser: MindUser = {
    id: "usr-reg1",
    name: "John Doe",
    email: "john@example.com",
    role: "user",
  };

  const mockLogs = [
    {
      id: "safe-001",
      timestamp: "2026-10-19T10:00:00Z",
      session_id: "ses-101",
      user_id: "usr-abc",
      tier: 1,
      rule_or_model: "crisis_rules:explicit_suicide",
      category: "self-harm",
      action_taken: "hotline_shown_LLM_bypassed",
      message_excerpt: "I want to [REDACTED] myself [hash:abc12345]",
      resolved: false,
      admin_note: "",
    },
    {
      id: "safe-002",
      timestamp: "2026-10-19T10:30:00Z",
      session_id: "ses-102",
      user_id: "guest-xyz789",
      tier: 2,
      rule_or_model: "crisis_detector.joblib",
      category: "homicide/threat-to-others",
      confidence: 0.92,
      action_taken: "escalated",
      message_excerpt: "I will [REDACTED] them [hash:def67890]",
      resolved: true,
      admin_note: "Clinician checked - false alarm",
    },
  ];

  const mockStats = {
    total_flags: 12,
    unresolved_count: 5,
    resolved_count: 7,
    last_7_days: {
      total: 8,
      tier_1: 4,
      tier_2: 3,
      tier_3: 1,
    },
    last_30_days: {
      total: 12,
      tier_1: 6,
      tier_2: 4,
      tier_3: 2,
    },
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    globalThis.fetch = vi.fn().mockImplementation((url: string, options?: any) => {
      if (options?.method === "PATCH") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            data: {
              ...mockLogs[0],
              resolved: true,
              admin_note: "Reviewed in test",
            },
          }),
        });
      }

      return Promise.resolve({
        ok: true,
        json: async () => ({
          success: true,
          data: {
            logs: mockLogs,
            total: 2,
            page: 1,
            limit: 15,
            total_pages: 1,
            stats: mockStats,
          },
        }),
      });
    }) as any;
  });

  it("renders access required gate for non-admin user", async () => {
    await act(async () => {
      render(<AdminSafetyLogs user={regularUser} token="user-token" />);
    });

    expect(screen.getByText(/Administrator Access Required/i)).toBeDefined();
    expect(screen.getByRole("button", { name: /Sign In as Administrator/i })).toBeDefined();
  });

  it("renders crisis logs table and stats for admin user", async () => {
    await act(async () => {
      render(<AdminSafetyLogs user={adminUser} token="admin-token" />);
    });

    // Check title and badges
    expect(screen.getByText(/Crisis Safety Event Logs/i)).toBeDefined();
    expect(screen.getByText(/Admin Audit/i)).toBeDefined();

    // Check stats cards
    expect(screen.getByText(/Total Crisis Flags/i)).toBeDefined();
    expect(screen.getAllByText("12").length).toBeGreaterThan(0); // total flags
    expect(screen.getByText("5")).toBeDefined(); // unresolved count

    // Check rows rendered
    expect(screen.getByText(/crisis_rules:explicit_suicide/i)).toBeDefined();
    expect(screen.getByText(/crisis_detector.joblib/i)).toBeDefined();
    expect(screen.getByText(/Tier 1 \(Regex\)/i)).toBeDefined();
    expect(screen.getByText(/Tier 2 \(ML\)/i)).toBeDefined();
  });

  it("allows filtering by tier and status", async () => {
    await act(async () => {
      render(<AdminSafetyLogs user={adminUser} token="admin-token" />);
    });

    const tierSelect = screen.getByLabelText(/Detection Tier/i);
    await act(async () => {
      fireEvent.change(tierSelect, { target: { value: "1" } });
    });

    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining("tier=1"),
      expect.any(Object)
    );
  });

  it("opens review modal, updates resolved status and note, and sends PATCH request", async () => {
    await act(async () => {
      render(<AdminSafetyLogs user={adminUser} token="admin-token" />);
    });

    const reviewButtons = screen.getAllByRole("button", { name: /Review/i });
    await act(async () => {
      fireEvent.click(reviewButtons[0]);
    });

    // Modal is open
    expect(screen.getByText(/Review Crisis Event Record/i)).toBeDefined();
    expect(screen.getByText("safe-001")).toBeDefined();

    // Check resolution checkbox
    const resolveCheckbox = screen.getByLabelText(/Mark as Reviewed & Resolved/i);
    fireEvent.click(resolveCheckbox);

    // Enter admin note
    const noteInput = screen.getByLabelText(/Clinician \/ Admin Audit Note/i);
    fireEvent.change(noteInput, { target: { value: "Reviewed in test" } });

    // Click Save Review
    const saveButton = screen.getByRole("button", { name: /Save Review/i });
    await act(async () => {
      fireEvent.click(saveButton);
    });

    // Verify PATCH was called
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/admin/safety-logs/safe-001",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          resolved: true,
          admin_note: "Reviewed in test",
        }),
      })
    );
  });
});
