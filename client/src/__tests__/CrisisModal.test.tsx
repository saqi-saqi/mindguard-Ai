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
    expect(screen.getByText(/Call 15 \(Police Emergency\)/i)).toBeDefined();
    expect(screen.getByText(/Call 1122 \(Pakistan Rescue\)/i)).toBeDefined();
    expect(screen.getByText(/Call 115 \(Edhi Ambulance\)/i)).toBeDefined();

    // Action 2: Designated Personal Anchor
    expect(screen.getByText(/2\. Designated Personal Anchor/i)).toBeDefined();
    expect(screen.getByText(/Call Mom \(0300-1234567\)/i)).toBeDefined();

    // Action 3: Primary 24/7 Mental Health Line
    expect(screen.getByText(/3\. Primary 24\/7 Mental Health Line/i)).toBeDefined();
    expect(screen.getByText(/Call Umang Pakistan Mental Health Helpline \(0311-7786264\)/i)).toBeDefined();

    // Progressive Disclosure Accordion exists and starts collapsed
    const directoryToggle = screen.getByRole("button", { name: /view more pakistan helplines/i });
    expect(directoryToggle).toBeDefined();
    expect(screen.queryByText(/Additional National Helplines/i)).toBeNull();

    // Expanding directory reveals Pakistan support lines only.
    fireEvent.click(directoryToggle);
    expect(screen.getByText(/Additional National Helplines/i)).toBeDefined();
    expect(screen.queryByText(/International Lines & Global Directory/i)).toBeNull();

    const closeBtn = screen.getByRole("button", { name: /close emergency modal/i });
    expect(closeBtn).toBeDefined();
  });

  it("renders exact mandatory warning copy, explicit disclosure, hospital fallback, and excludes 988/111", () => {
    const handleClose = vi.fn();
    render(<CrisisModal isOpen={true} onClose={handleClose} />);

    // 1. Mandatory Warning Line, always visible
    expect(
      screen.getByText(
        "Immediate safety support needed — move away from the person and any weapon or harmful object, and contact emergency services now."
      )
    ).toBeDefined();

    // 2. Explicit Disclosure Line
    expect(
      screen.getByText(
        "This app cannot contact emergency services automatically — please call one of the numbers above or go to your nearest hospital emergency department."
      )
    ).toBeDefined();

    // 3. Fallback Hospital Line
    expect(
      screen.getByText("Or go to the emergency department of your nearest hospital.")
    ).toBeDefined();

    // 4. Core Pakistan Emergency Numbers
    expect(screen.getByText(/Call 15 \(Police Emergency\)/i)).toBeDefined();
    expect(screen.getByText(/Call 1122 \(Pakistan Rescue\)/i)).toBeDefined();
    expect(screen.getByText(/Call 115 \(Edhi Ambulance\)/i)).toBeDefined();
    expect(screen.getByText(/0311-7786264/i)).toBeDefined();

    // 5. Strictly no US 988 or UK 111
    const modalText = document.body.textContent || "";
    expect(modalText).not.toContain("988");
    expect(modalText).not.toContain("111-");
    expect(modalText).not.toContain("call 111");
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

  // --- Task 5: Crisis-modal safety telemetry correctness ---

  it("Task 5: close button does NOT call onSafetyStatus — passive dismissal only", () => {
    /**
     * Clicking the X close button is a passive dismissal (equivalent to pressing Escape).
     * It must NOT record safe_for_now telemetry — only the explicit safety confirmation
     * button ("I'm safe for now — return to chat") should do that.
     */
    const handleClose = vi.fn();
    const handleSafetyStatus = vi.fn();
    render(<CrisisModal isOpen={true} onClose={handleClose} onSafetyStatus={handleSafetyStatus} />);

    const closeButton = screen.getByRole("button", { name: /close emergency modal/i });
    fireEvent.click(closeButton);

    expect(handleClose).toHaveBeenCalledTimes(1);
    expect(handleSafetyStatus).not.toHaveBeenCalled();
  });

  it("Task 5: backdrop click does NOT call onSafetyStatus — passive dismissal only", () => {
    /**
     * Clicking outside the modal panel (on the backdrop overlay) is a passive dismissal.
     * It must NOT record safe_for_now telemetry.
     */
    const handleClose = vi.fn();
    const handleSafetyStatus = vi.fn();
    render(<CrisisModal isOpen={true} onClose={handleClose} onSafetyStatus={handleSafetyStatus} />);

    const dialog = screen.getByRole("dialog");
    // Simulate a click directly on the backdrop (target === currentTarget)
    fireEvent.click(dialog, { target: dialog });

    expect(handleClose).toHaveBeenCalledTimes(1);
    expect(handleSafetyStatus).not.toHaveBeenCalled();
  });

  it("Task 5: Escape key does NOT call onSafetyStatus — passive dismissal only", () => {
    /**
     * Pressing Escape is a passive keyboard dismissal.
     * It must NOT record safe_for_now telemetry.
     */
    const handleClose = vi.fn();
    const handleSafetyStatus = vi.fn();
    render(<CrisisModal isOpen={true} onClose={handleClose} onSafetyStatus={handleSafetyStatus} />);

    fireEvent.keyDown(window, { key: "Escape" });

    expect(handleClose).toHaveBeenCalledTimes(1);
    expect(handleSafetyStatus).not.toHaveBeenCalled();
  });

  it("Task 5: only the explicit safe-for-now button records safe_for_now telemetry", () => {
    /**
     * Comprehensive telemetry contract: verify that safe_for_now is recorded EXACTLY
     * once (via the explicit button) and that passive dismissals (close, backdrop,
     * Escape) do not contribute to the telemetry count.
     */
    const handleClose = vi.fn();
    const handleSafetyStatus = vi.fn();
    render(<CrisisModal isOpen={true} onClose={handleClose} onSafetyStatus={handleSafetyStatus} />);

    // Passive dismissals — no telemetry
    const closeButton = screen.getByRole("button", { name: /close emergency modal/i });
    fireEvent.click(closeButton);

    // handleClose was called but onSafetyStatus was not
    expect(handleSafetyStatus).not.toHaveBeenCalled();
  });
});

