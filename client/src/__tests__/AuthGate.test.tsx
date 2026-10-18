import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import React from "react";
import AuthGateModal from "../components/AuthGateModal";
import useAuthGate, { AuthGate } from "../components/useAuthGate";

describe("AuthGate Guard & AuthGateModal", () => {
  it("renders AuthGateModal with accessible ARIA attributes and labels", () => {
    const onClose = vi.fn();
    const onLogin = vi.fn();
    const onRegister = vi.fn();

    render(
      <AuthGateModal
        isOpen={true}
        onClose={onClose}
        onLogin={onLogin}
        onRegister={onRegister}
        title="Custom Sign In Required"
        description="Please authenticate to continue."
      />
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeDefined();
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-labelledby")).toBe("auth-gate-modal-title");
    expect(dialog.getAttribute("aria-describedby")).toBe("auth-gate-modal-desc");

    expect(screen.getByText("Custom Sign In Required")).toBeDefined();
    expect(screen.getByText("Please authenticate to continue.")).toBeDefined();

    const loginBtn = screen.getByRole("button", { name: /^Log In$/i });
    const registerBtn = screen.getByRole("button", { name: /^Register$/i });
    const dismissBtn = screen.getByRole("button", { name: /Stay on page \(Dismiss\)/i });

    expect(loginBtn).toBeDefined();
    expect(registerBtn).toBeDefined();
    expect(dismissBtn).toBeDefined();

    // Trigger Login
    fireEvent.click(loginBtn);
    expect(onLogin).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("handles Escape key and outside click to dismiss modal", () => {
    const onClose = vi.fn();

    const { container } = render(
      <AuthGateModal
        isOpen={true}
        onClose={onClose}
      />
    );

    // Escape key
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);

    // Outside click (backdrop)
    const backdrop = container.firstChild as HTMLElement;
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("useAuthGate hook blocks action when unauthenticated and opens modal", () => {
    const actionSpy = vi.fn();
    const onNavigateToAuth = vi.fn();

    function TestComponent({ isAuth }: { isAuth: boolean }) {
      const { requireAuth, AuthModal } = useAuthGate({
        isAuthenticated: isAuth,
        onNavigateToAuth,
      });

      return (
        <div>
          <button type="button" onClick={requireAuth(actionSpy)}>
            Protected Action
          </button>
          <AuthModal />
        </div>
      );
    }

    const { rerender } = render(<TestComponent isAuth={false} />);

    // Click protected action as unauthenticated user
    const actionBtn = screen.getByRole("button", { name: /Protected Action/i });
    fireEvent.click(actionBtn);

    // Action should NOT be executed
    expect(actionSpy).not.toHaveBeenCalled();

    // Modal should be displayed
    expect(screen.getByRole("dialog")).toBeDefined();
    expect(screen.getByText(/Sign In Required/i)).toBeDefined();

    // Now re-render as authenticated
    rerender(<TestComponent isAuth={true} />);

    // Click protected action as authenticated user
    fireEvent.click(actionBtn);
    expect(actionSpy).toHaveBeenCalledTimes(1);
  });

  it("AuthGate wrapper component works declaratively", () => {
    const actionSpy = vi.fn();
    const onNavigateToAuth = vi.fn();

    render(
      <AuthGate isAuthenticated={false} onNavigateToAuth={onNavigateToAuth}>
        {({ requireAuth }) => (
          <button type="button" onClick={requireAuth(actionSpy)}>
            Gated Trigger
          </button>
        )}
      </AuthGate>
    );

    const btn = screen.getByRole("button", { name: /Gated Trigger/i });
    fireEvent.click(btn);

    expect(actionSpy).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeDefined();
  });
});
