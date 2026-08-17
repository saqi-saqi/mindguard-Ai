import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import React from "react";
import CrisisModal from "../components/CrisisModal";

describe("CrisisModal Accessibility & Clinical Hierarchy", () => {
  it("renders with correct ARIA roles, labels, and clinical hierarchy when open", () => {
    const handleClose = vi.fn();
    render(<CrisisModal isOpen={true} onClose={handleClose} />);

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeDefined();
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-labelledby")).toBe("crisis-modal-title");
    expect(dialog.getAttribute("aria-describedby")).toBe("crisis-modal-desc");

    const title = screen.getByText("You Are Not Alone");
    expect(title.id).toBe("crisis-modal-title");

    // Level 1 Emergency Services should be rendered at the top
    expect(screen.getByText(/Level 1: Immediate Emergency Services/i)).toBeDefined();
    expect(screen.getByText(/Call 1122 \(Pakistan Rescue\)/i)).toBeDefined();
    expect(screen.getByText(/Call 988 \(US \/ Canada Lifeline\)/i)).toBeDefined();

    // 24/7 Regional Crisis Helplines
    expect(screen.getByText(/Umang Pakistan Mental Health Helpline/i)).toBeDefined();

    const closeBtn = screen.getByRole("button", { name: /close emergency modal/i });
    expect(closeBtn).toBeDefined();
  });

  it("does not render when isOpen is false", () => {
    const handleClose = vi.fn();
    render(<CrisisModal isOpen={false} onClose={handleClose} />);

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("triggers onClose when Escape key is pressed", () => {
    const handleClose = vi.fn();
    render(<CrisisModal isOpen={true} onClose={handleClose} />);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it("keeps keyboard focus within the modal", () => {
    const handleClose = vi.fn();
    render(<CrisisModal isOpen={true} onClose={handleClose} />);

    const closeButton = screen.getByRole("button", { name: /close emergency modal/i });
    const safeButton = screen.getByRole("button", { name: /i'm safe for now/i });
    safeButton.focus();
    fireEvent.keyDown(window, { key: "Tab" });

    expect(document.activeElement).toBe(closeButton);
  });

  it("toggles the optional breathing tool without blocking crisis resources", () => {
    const handleClose = vi.fn();
    render(<CrisisModal isOpen={true} onClose={handleClose} />);

    const toggleBtn = screen.getByRole("button", { name: /open 4-7-8 tool/i });
    fireEvent.click(toggleBtn);

    expect(screen.getByText(/4s Inhale, 7s Hold, 8s Exhale/i)).toBeDefined();
    const startBtn = screen.getByRole("button", { name: /start/i });
    fireEvent.click(startBtn);
    expect(screen.getByRole("button", { name: /pause/i })).toBeDefined();
  });

  it("calls onSafetyStatus when 'I\\'m safe for now' is clicked", () => {
    const handleClose = vi.fn();
    const handleSafetyStatus = vi.fn();
    render(<CrisisModal isOpen={true} onClose={handleClose} onSafetyStatus={handleSafetyStatus} />);

    const safeButton = screen.getByRole("button", { name: /i'm safe for now/i });
    fireEvent.click(safeButton);

    expect(handleSafetyStatus).toHaveBeenCalledWith("safe_for_now");
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
