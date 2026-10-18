import React, { useEffect, useRef } from "react";
import { Lock, X, LogIn, UserPlus } from "lucide-react";

export interface AuthGateModalProps {
  isOpen: boolean;
  onClose: () => void;
  onLogin?: () => void;
  onRegister?: () => void;
  title?: string;
  description?: string;
  actionName?: string;
}

export default function AuthGateModal({
  isOpen,
  onClose,
  onLogin,
  onRegister,
  title,
  description,
  actionName,
}: AuthGateModalProps) {
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    previousFocusRef.current = document.activeElement as HTMLElement;
    closeButtonRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab") return;

      const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (!focusable?.length) {
        e.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      previousFocusRef.current?.focus();
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="auth-gate-modal-title"
      aria-describedby="auth-gate-modal-desc"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
      className="fade-in fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-xs font-sans"
    >
      <div className="relative w-full max-w-md rounded-2xl border border-slate-200/90 bg-white p-6 shadow-2xl space-y-5">
        <button
          ref={closeButtonRef}
          type="button"
          onClick={onClose}
          aria-label="Close dialog"
          className="absolute right-4 top-4 grid size-8 place-items-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
        >
          <X className="size-4" />
        </button>

        <div className="flex items-center gap-3 pr-8">
          <div className="grid size-11 shrink-0 place-items-center rounded-xl bg-indigo-50 border border-indigo-100 text-indigo-600">
            <Lock className="size-5" />
          </div>
          <div>
            <h3 id="auth-gate-modal-title" className="text-base font-bold text-slate-900 font-heading">
              {title || "Sign In Required"}
            </h3>
            <p className="text-xs text-slate-500 font-medium">
              MindGuard Guest Mode
            </p>
          </div>
        </div>

        <div
          id="auth-gate-modal-desc"
          className="rounded-xl border border-indigo-50 bg-indigo-50/50 p-3.5 text-xs text-slate-700 leading-relaxed space-y-1.5"
        >
          <p className="font-medium text-indigo-950">
            {description ||
              (actionName
                ? `You need an account to ${actionName}. Please log in or create an account to save your data securely.`
                : "You need to be signed in to perform this action. Log in or create an account to securely save check-ins, manage settings, and preserve your data.")}
          </p>
          <p className="text-[11px] text-slate-500 font-normal">
            Your current view and inputs remain untouched if you wish to stay on this page.
          </p>
        </div>

        <div className="flex flex-col gap-2.5 pt-1">
          <button
            type="button"
            onClick={() => {
              onClose();
              onLogin?.();
            }}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-bold text-white shadow-xs hover:bg-indigo-500 transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          >
            <LogIn className="size-4" />
            <span>Log In</span>
          </button>

          <button
            type="button"
            onClick={() => {
              onClose();
              onRegister?.();
            }}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-indigo-200 bg-white px-4 py-2.5 text-xs font-bold text-indigo-700 hover:bg-indigo-50 transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          >
            <UserPlus className="size-4" />
            <span>Register</span>
          </button>

          <button
            type="button"
            onClick={onClose}
            className="w-full text-center text-xs font-medium text-slate-500 hover:text-slate-800 py-1 transition-colors cursor-pointer focus-visible:outline-none"
          >
            Stay on page (Dismiss)
          </button>
        </div>
      </div>
    </div>
  );
}
