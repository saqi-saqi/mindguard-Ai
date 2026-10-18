import React, { useState, useCallback } from "react";
import AuthGateModal from "./AuthGateModal";

export interface UseAuthGateOptions {
  isAuthenticated: boolean;
  onNavigateToAuth?: (mode: "login" | "register") => void;
  title?: string;
  description?: string;
}

export function useAuthGate({
  isAuthenticated,
  onNavigateToAuth,
  title,
  description,
}: UseAuthGateOptions) {
  const [isOpen, setIsOpen] = useState(false);

  const requireAuth = useCallback(
    <T extends (...args: any[]) => any>(action: T) => {
      return (...args: Parameters<T>): ReturnType<T> | void => {
        if (isAuthenticated) {
          return action(...args);
        }
        const event = args[0];
        if (event && typeof event.preventDefault === "function") {
          event.preventDefault();
        }
        if (event && typeof event.stopPropagation === "function") {
          event.stopPropagation();
        }
        setIsOpen(true);
      };
    },
    [isAuthenticated]
  );

  const AuthModal = useCallback(() => {
    return (
      <AuthGateModal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onLogin={() => {
          setIsOpen(false);
          onNavigateToAuth?.("login");
        }}
        onRegister={() => {
          setIsOpen(false);
          onNavigateToAuth?.("register");
        }}
        title={title}
        description={description}
      />
    );
  }, [isOpen, onNavigateToAuth, title, description]);

  return {
    requireAuth,
    isAuthModalOpen: isOpen,
    openAuthModal: () => setIsOpen(true),
    closeAuthModal: () => setIsOpen(false),
    AuthModal,
  };
}

export interface AuthGateProps {
  isAuthenticated: boolean;
  onNavigateToAuth?: (mode: "login" | "register") => void;
  title?: string;
  description?: string;
  children: (props: {
    requireAuth: <T extends (...args: any[]) => any>(action: T) => (...args: Parameters<T>) => ReturnType<T> | void;
    openAuthModal: () => void;
    isAuthModalOpen: boolean;
  }) => React.ReactNode;
}

export function AuthGate({
  isAuthenticated,
  onNavigateToAuth,
  title,
  description,
  children,
}: AuthGateProps) {
  const { requireAuth, openAuthModal, isAuthModalOpen, AuthModal } = useAuthGate({
    isAuthenticated,
    onNavigateToAuth,
    title,
    description,
  });

  return (
    <>
      {children({ requireAuth, openAuthModal, isAuthModalOpen })}
      <AuthModal />
    </>
  );
}

export default useAuthGate;
