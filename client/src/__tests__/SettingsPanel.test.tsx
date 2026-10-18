import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import SettingsPanel from "../components/SettingsPanel";
import type { MindUser } from "../components/types";

describe("SettingsPanel Transparency & Safety Gates", () => {
  const sampleUser: MindUser = {
    id: "user-123",
    name: "Ayesha Khan",
    email: "ayesha@example.com",
    trusted_contact: {
      name: "Ali Khan",
      phone: "+923001234567",
      relationship: "Brother"
    },
    settings: {
      consent_given: true,
      retention_enabled: true,
      retention_days: 60,
      locale: "pakistan"
    }
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders data storage transparency breakdown and retention explanations", () => {
    render(
      <SettingsPanel
        user={sampleUser}
        token="valid-token"
        onUpdated={vi.fn()}
        onAccountDeleted={vi.fn()}
      />
    );

    expect(screen.getByText(/What MindGuard Stores & Why/i)).toBeDefined();
    expect(screen.getByText(/Chat messages:/i)).toBeDefined();
    expect(screen.getByText(/Mood check-ins:/i)).toBeDefined();
    expect(screen.getByText(/Records older than 60 days are automatically purged/i)).toBeDefined();
  });

  it("displays mandatory safety notice regarding trusted contact automation", () => {
    render(
      <SettingsPanel
        user={sampleUser}
        token="valid-token"
        onUpdated={vi.fn()}
        onAccountDeleted={vi.fn()}
      />
    );

    expect(
      screen.getByText(/MindGuard never contacts this person automatically. Any call or message requires your explicit action./i)
    ).toBeDefined();
  });

  it("masks phone number by default and allows toggling unmask preview", () => {
    render(
      <SettingsPanel
        user={sampleUser}
        token="valid-token"
        onUpdated={vi.fn()}
        onAccountDeleted={vi.fn()}
      />
    );

    const phoneInput = screen.getByDisplayValue("+923001234567");
    expect(phoneInput.getAttribute("type")).toBe("password");
    expect(screen.getByText(/Masked preview: \+92 ••• ••• 567/i)).toBeDefined();

    const toggleMaskBtn = screen.getByRole("button", { name: /show/i });
    fireEvent.click(toggleMaskBtn);

    expect(phoneInput.getAttribute("type")).toBe("text");
  });

  it("enforces deliberate two-step typed phrase ('DELETE') before enabling account deletion", async () => {
    const onAccountDeleted = vi.fn();
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true })
    });
    globalThis.fetch = mockFetch as any;

    render(
      <SettingsPanel
        user={sampleUser}
        token="valid-token"
        onUpdated={vi.fn()}
        onAccountDeleted={onAccountDeleted}
      />
    );

    const openDeleteBtn = screen.getByRole("button", { name: /Delete Account/i });
    fireEvent.click(openDeleteBtn);

    expect(screen.getByText(/Confirm Account & Data Deletion/i)).toBeDefined();

    const deleteSubmitBtn = screen.getByRole("button", { name: /Permanently Delete/i });
    expect(deleteSubmitBtn.getAttribute("disabled")).toBeDefined();

    const confirmInput = screen.getByPlaceholderText("DELETE");
    fireEvent.change(confirmInput, { target: { value: "DELETE" } });

    expect(deleteSubmitBtn.getAttribute("disabled")).toBeNull();

    fireEvent.click(deleteSubmitBtn);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/auth/account",
        expect.objectContaining({
          method: "DELETE",
          headers: expect.objectContaining({ Authorization: "Bearer valid-token" })
        })
      );
      expect(onAccountDeleted).toHaveBeenCalled();
    });
  });

  it("saves settings and trusted contact changes and displays success feedback", async () => {
    const onUpdated = vi.fn();
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          settings: { consent_given: true, retention_enabled: true, retention_days: 90, locale: "pakistan" }
        }
      })
    });
    globalThis.fetch = mockFetch as any;

    render(
      <SettingsPanel
        user={sampleUser}
        token="valid-token"
        onUpdated={onUpdated}
        onAccountDeleted={vi.fn()}
      />
    );

    const saveBtn = screen.getByRole("button", { name: /Save Settings & Preferences/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
      expect(screen.getByText(/Settings and privacy preferences updated successfully/i)).toBeDefined();
    });
  });

  describe("Guest-Mode Auth Gate on Privacy & Settings", () => {
    it("intercepts Save Settings & Preferences when guest user: opens modal and prevents API save", async () => {
      const mockFetch = vi.fn();
      globalThis.fetch = mockFetch as any;
      const onNavigateToAuth = vi.fn();

      render(
        <SettingsPanel
          user={null}
          token=""
          onNavigateToAuth={onNavigateToAuth}
        />
      );

      const saveBtn = screen.getByRole("button", { name: /Save Settings & Preferences/i });
      fireEvent.click(saveBtn);

      // Verify AuthGateModal opens
      expect(screen.getByRole("dialog")).toBeDefined();
      expect(screen.getByText(/Sign In Required/i)).toBeDefined();
      expect(screen.getByRole("button", { name: /^Log In$/i })).toBeDefined();
      expect(screen.getByRole("button", { name: /^Register$/i })).toBeDefined();

      // Original API save must NOT have been called
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it("intercepts Export JSON when guest user: opens modal and prevents export fetch", async () => {
      const mockFetch = vi.fn();
      globalThis.fetch = mockFetch as any;
      const onNavigateToAuth = vi.fn();

      render(
        <SettingsPanel
          user={null}
          token=""
          onNavigateToAuth={onNavigateToAuth}
        />
      );

      const exportBtn = screen.getByRole("button", { name: /Export JSON/i });
      fireEvent.click(exportBtn);

      // Verify AuthGateModal opens
      expect(screen.getByRole("dialog")).toBeDefined();
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it("intercepts Delete Account when guest user: opens auth modal and does NOT open delete confirmation dialog", async () => {
      const onNavigateToAuth = vi.fn();

      render(
        <SettingsPanel
          user={null}
          token=""
          onNavigateToAuth={onNavigateToAuth}
        />
      );

      const deleteBtn = screen.getByRole("button", { name: /Delete Account/i });
      fireEvent.click(deleteBtn);

      // Auth gate modal should be open
      expect(screen.getByText(/Sign In Required/i)).toBeDefined();
      // Delete confirmation modal should NOT be open
      expect(screen.queryByText(/Confirm Account & Data Deletion/i)).toBeNull();
    });

    it("modal allows navigating to login and register, and dismissing", async () => {
      const onNavigateToAuth = vi.fn();

      render(
        <SettingsPanel
          user={null}
          token=""
          onNavigateToAuth={onNavigateToAuth}
        />
      );

      const saveBtn = screen.getByRole("button", { name: /Save Settings & Preferences/i });
      fireEvent.click(saveBtn);

      // Click Log In
      const loginBtn = screen.getByRole("button", { name: /^Log In$/i });
      fireEvent.click(loginBtn);
      expect(onNavigateToAuth).toHaveBeenCalledWith("login");
      expect(screen.queryByRole("dialog")).toBeNull();

      // Open again and click Register
      fireEvent.click(saveBtn);
      const registerBtn = screen.getByRole("button", { name: /^Register$/i });
      fireEvent.click(registerBtn);
      expect(onNavigateToAuth).toHaveBeenCalledWith("register");
      expect(screen.queryByRole("dialog")).toBeNull();

      // Open again and dismiss
      fireEvent.click(saveBtn);
      const dismissBtn = screen.getByRole("button", { name: /Stay on page \(Dismiss\)/i });
      fireEvent.click(dismissBtn);
      expect(screen.queryByRole("dialog")).toBeNull();
    });

    it("allows authenticated user to click Export JSON without auth modal", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: { export: true } })
      });
      globalThis.fetch = mockFetch as any;

      // Mock URL.createObjectURL and revokeObjectURL
      window.URL.createObjectURL = vi.fn().mockReturnValue("blob:mock");
      window.URL.revokeObjectURL = vi.fn();

      render(
        <SettingsPanel
          user={sampleUser}
          token="valid-token"
        />
      );

      const exportBtn = screen.getByRole("button", { name: /Export JSON/i });
      fireEvent.click(exportBtn);

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          "/api/user/export",
          expect.objectContaining({
            headers: expect.objectContaining({ Authorization: "Bearer valid-token" })
          })
        );
      });
      expect(screen.queryByText(/Sign In Required/i)).toBeNull();
    });
  });
});
