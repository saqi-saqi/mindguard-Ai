import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import AuthScreen from "../components/AuthScreen";

describe("AuthScreen Component Quality & Authentication Flow", () => {
  const mockOnLogin = vi.fn();

  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("renders in Sign In mode by default with email and password inputs", () => {
    render(<AuthScreen onLogin={mockOnLogin} />);

    expect(screen.getByText("Welcome Back to MindGuard")).toBeDefined();
    expect(screen.getByPlaceholderText("user@example.com")).toBeDefined();
    expect(screen.getByPlaceholderText("••••••••")).toBeDefined();
    expect(screen.getByRole("button", { name: /Sign In/i })).toBeDefined();
    expect(screen.getByText(/Don't have an account yet\?/i)).toBeDefined();
  });

  it("validates required email and password on submission", async () => {
    render(<AuthScreen onLogin={mockOnLogin} />);

    const submitBtn = screen.getByRole("button", { name: /Sign In/i });
    fireEvent.submit(submitBtn.closest("form")!);

    expect(await screen.findByText(/Email address and password are required/i)).toBeDefined();
    expect(mockOnLogin).not.toHaveBeenCalled();
  });

  it("toggles to Sign Up mode and enforces name, consent, and password length", async () => {
    render(<AuthScreen onLogin={mockOnLogin} />);

    // Toggle to registration mode
    const toggleBtn = screen.getByRole("button", { name: /Register Now/i });
    fireEvent.click(toggleBtn);

    expect(screen.getByText("Create Your Account")).toBeDefined();
    expect(screen.getByPlaceholderText("Muhammad Saqib")).toBeDefined();

    // 1. Fill email and password without name
    const emailInput = screen.getByPlaceholderText("user@example.com");
    const passInput = screen.getByPlaceholderText("••••••••");
    fireEvent.change(emailInput, { target: { value: "test@example.com" } });
    fireEvent.change(passInput, { target: { value: "secret123" } });

    const registerBtn = screen.getByRole("button", { name: /Create Account/i });
    fireEvent.submit(registerBtn.closest("form")!);

    expect(await screen.findByText(/Full name is required for registration/i)).toBeDefined();

    // 2. Fill name but leave consent unchecked
    const nameInput = screen.getByPlaceholderText("Muhammad Saqib");
    fireEvent.change(nameInput, { target: { value: "Test User" } });
    fireEvent.submit(registerBtn.closest("form")!);

    expect(await screen.findByText(/Please confirm consent before creating an account/i)).toBeDefined();

    // 3. Password shorter than 6 characters
    fireEvent.change(passInput, { target: { value: "123" } });
    const consentCheckbox = screen.getByRole("checkbox");
    fireEvent.click(consentCheckbox);
    fireEvent.submit(registerBtn.closest("form")!);

    expect(await screen.findByText(/Password must be at least 6 characters long/i)).toBeDefined();
  });

  it("successfully logs in, saves token in localStorage, and calls onLogin", async () => {
    const fakeToken = "jwt-login-token-998877";
    const fakeUser = {
      id: "usr-12345",
      name: "Logged In User",
      email: "user@example.com",
      role: "user",
      settings: { consent_given: true, retention_days: 30, retention_enabled: true, locale: "pakistan" }
    };

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: { token: fakeToken, user: fakeUser }
      })
    });
    globalThis.fetch = mockFetch as any;

    render(<AuthScreen onLogin={mockOnLogin} />);

    fireEvent.change(screen.getByPlaceholderText("user@example.com"), { target: { value: "user@example.com" } });
    fireEvent.change(screen.getByPlaceholderText("••••••••"), { target: { value: "ValidPass!123" } });

    fireEvent.click(screen.getByRole("button", { name: /Sign In/i }));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/auth/login",
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: "user@example.com", password: "ValidPass!123" })
        })
      );
    });

    await waitFor(() => {
      expect(localStorage.getItem("mg_token")).toBe(fakeToken);
      expect(mockOnLogin).toHaveBeenCalledWith(fakeUser, fakeToken);
    });
  });

  it("displays server error message when credentials are invalid", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({
        success: false,
        error: { message: "Invalid email or password" }
      })
    });
    globalThis.fetch = mockFetch as any;

    render(<AuthScreen onLogin={mockOnLogin} />);

    fireEvent.change(screen.getByPlaceholderText("user@example.com"), { target: { value: "wrong@example.com" } });
    fireEvent.change(screen.getByPlaceholderText("••••••••"), { target: { value: "wrongpass" } });

    fireEvent.click(screen.getByRole("button", { name: /Sign In/i }));

    expect(await screen.findByText(/Invalid email or password/i)).toBeDefined();
    expect(localStorage.getItem("mg_token")).toBeNull();
    expect(mockOnLogin).not.toHaveBeenCalled();
  });

  it("handles offline network failure gracefully", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("Network connection lost"));

    render(<AuthScreen onLogin={mockOnLogin} />);

    fireEvent.change(screen.getByPlaceholderText("user@example.com"), { target: { value: "user@example.com" } });
    fireEvent.change(screen.getByPlaceholderText("••••••••"), { target: { value: "ValidPass!123" } });

    fireEvent.click(screen.getByRole("button", { name: /Sign In/i }));

    expect(await screen.findByText(/Network connection lost/i)).toBeDefined();
    expect(localStorage.getItem("mg_token")).toBeNull();
  });
});
