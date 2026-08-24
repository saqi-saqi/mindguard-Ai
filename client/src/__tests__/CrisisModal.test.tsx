import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import React from "react";
import CrisisModal from "../components/CrisisModal";

describe("CrisisModal Accessibility & Clinical Hierarchy", () => {
  it("renders with 3-action acute triage hierarchy and accessible ARIA attributes", () => {
    const handleClose = vi.fn();
    render(
      <CrisisModal
        isOpen={true}
        onClose={handleClose}
        trustedContact={{ name: "Mom", phone: "0300-1234567", relationship: "Parent" }}
      />
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeDefined();
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-labelledby")).toBe("crisis-modal-title");
    expect(dialog.getAttribute("aria-describedby")).toBe("crisis-modal-desc");

    const title = screen.getByText("You Are Not Alone");
    expect(title.id).toBe("crisis-modal-title");

    // Action 1: Immediate Emergency Dispatch
    expect(screen.getByText(/1\. Emergency Dispatch/i)).toBeDefined();
    expect(screen.getByText(/Call 1122 \(Pakistan Rescue\)/i)).toBeDefined();
    expect(screen.getByText(/Call 988 \(US \/ Canada Lifeline\)/i)).toBeDefined();

    // Action 2: Designated Personal Anchor
    expect(screen.getByText(/2\. Designated Personal Anchor/i)).toBeDefined();
    expect(screen.getByText(/Call Mom \(0300-1234567\)/i)).toBeDefined();

    // Action 3: Primary 24/7 Mental Health Line
    expect(screen.getByText(/3\. Primary 24\/7 Mental Health Line/i)).toBeDefined();
    expect(screen.getByText(/Call Umang Pakistan Mental Health Helpline \(0311-7786264\)/i)).toBeDefined();

    // Progressive Disclosure Accordion exists and starts collapsed
    const directoryToggle = screen.getByRole("button", { name: /view more helplines/i });
    expect(directoryToggle).toBeDefined();
    expect(screen.queryByText(/Additional National Helplines/i)).toBeNull();

    // Expanding directory reveals auxiliary and international hotlines
    fireEvent.click(directoryToggle);
    expect(screen.getByText(/Additional National Helplines/i)).toBeDefined();
    expect(screen.getByText(/International Lines & Global Directory/i)).toBeDefined();

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
    const startBtn = screen.getByRole("button", { name: /start breathing/i });
    fireEvent.click(startBtn);
    expect(screen.getByRole("button", { name: /pause breathing/i })).toBeDefined();
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
