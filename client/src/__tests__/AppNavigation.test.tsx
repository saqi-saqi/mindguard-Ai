import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import App from "../App";

describe("App Navigation Flow", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    globalThis.fetch = vi.fn().mockImplementation((url) => {
      if (url.includes("/api/auth/me")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            data: {
              user: {
                id: "test-user",
                name: "Saqib",
                email: "saqib@test.com",
                settings: { retention_enabled: true, retention_days: 30, consent_given: true }
              }
            }
          })
        });
      }
      if (url.includes("/api/chat/sessions")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, data: { sessions: [] } })
        });
      }
      if (url.includes("/api/moods")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, data: { mood_logs: [] } })
        });
      }
      if (url.includes("/api/user/settings")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            data: { settings: { retention_enabled: true, retention_days: 30, consent_given: true } }
          })
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, data: {} })
      });
    }) as any;
  });

  it("opens directly to Sign In screen on startup by default", () => {
    render(<App />);
    expect(screen.getByText(/Welcome Back to MindGuard/i)).toBeDefined();
    expect(screen.getByRole("button", { name: /^Sign In$/i })).toBeDefined();
  });

  it("navigates to Privacy & Settings tab without throwing and shows Back to Chat button", async () => {
    render(<App />);

    // Click Privacy & Settings navigation button
    const settingsBtn = screen.getAllByRole("button", { name: /Privacy & Settings/i })[0];
    fireEvent.click(settingsBtn);

    // Verify SettingsPanel renders
    expect(await screen.findByRole("heading", { name: /Privacy & Settings/i })).toBeDefined();

    // Verify Back to Chat button renders
    const backBtn = screen.getByRole("button", { name: /Back to Chat/i });
    expect(backBtn).toBeDefined();

    // Click Back to Chat button
    fireEvent.click(backBtn);

    // Verify it navigates back to Chat
    expect(screen.getByText(/MindGuard Assistant/i)).toBeDefined();
  });
});
