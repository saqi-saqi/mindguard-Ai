import { useState } from "react";
import { Mail, Lock, User, HeartHandshake, ArrowRight, AlertCircle, CheckCircle2, RefreshCw } from "lucide-react";
import type { MindUser } from "./types";

interface AuthScreenProps {
  onLogin: (user: MindUser, token: string) => void;
}

export default function AuthScreen({ onLogin }: AuthScreenProps) {
  const [isLoginMode, setIsLoginMode] = useState(true);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [consentGiven, setConsentGiven] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    const cleanEmail = email.trim().toLowerCase();
    const cleanPassword = password.trim();

    if (!cleanEmail || !cleanPassword) {
      setErrorMsg("Email address and password are required.");
      return;
    }

    if (!isLoginMode && !name.trim()) {
      setErrorMsg("Full name is required for registration.");
      return;
    }
    if (!isLoginMode && !consentGiven) {
      setErrorMsg("Please confirm consent before creating an account.");
      return;
    }

    if (!isLoginMode && cleanPassword.length < 6) {
      setErrorMsg("Password must be at least 6 characters long.");
      return;
    }

    setIsLoading(true);

    try {
      const endpoint = isLoginMode ? "/api/auth/login" : "/api/auth/register";
      const payload = isLoginMode
        ? { email: cleanEmail, password: cleanPassword }
        : { name: name.trim(), email: cleanEmail, password: cleanPassword, consent_given: consentGiven };

      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      let resData: any = null;
      try {
        resData = await res.json();
      } catch {
        if (!res.ok) {
          throw new Error(`Server error (${res.status}): Backend server is offline or unreachable. Please ensure Python backend (app.py) is running.`);
        }
        throw new Error("Invalid or empty response received from server.");
      }

      if (res.ok && resData.success !== false) {
        const token = resData.data?.token || resData.token;
        const userData = resData.data?.user || resData.user;

        if (token && userData) {
          localStorage.setItem("mg_token", token);
          setSuccessMsg(isLoginMode ? "Signed in successfully!" : "Account registered successfully!");
          setTimeout(() => {
            onLogin(userData, token);
          }, 400);
        } else {
          throw new Error("Invalid response format from authentication server.");
        }
      } else {
        const errObj = resData.error || {};
        setErrorMsg(errObj.message || resData.message || "Authentication failed. Please check your inputs.");
      }
    } catch (err) {
      console.error("Auth API Error:", err);
      setErrorMsg((err as Error).message || "Unable to connect to authentication backend server.");
    } finally {
      setIsLoading(false);
    }
  };

  const fieldClass =
    "w-full rounded-xl border border-slate-300 bg-white py-3 pl-10 pr-4 text-sm text-slate-900 placeholder:text-slate-500 transition-all focus:border-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-100 font-sans";

  return (
    <div className="fade-in relative flex min-h-0 flex-1 items-center justify-center overflow-y-auto bg-slate-50 p-4 sm:p-6 font-sans">
      <div className="pointer-events-none absolute left-1/2 top-1/4 size-96 -translate-x-1/2 rounded-full bg-indigo-500/10 blur-3xl" />

      <div className="relative z-10 w-full max-w-md rounded-3xl border border-slate-200/90 bg-white p-6 shadow-xl sm:p-8">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-4 grid size-14 place-items-center rounded-2xl bg-gradient-to-tr from-indigo-600 to-indigo-500 text-white shadow-lg shadow-indigo-600/25">
            <HeartHandshake className="size-8" />
          </div>
          <h2 className="mb-1 text-2xl font-bold text-slate-900 font-heading">
            {isLoginMode ? "Welcome Back to MindGuard" : "Create Your Account"}
          </h2>
          <p className="text-xs text-slate-600 font-medium">
            {isLoginMode
              ? "Sign in to access your confidential mood logs & assistant"
              : "Join MindGuard for secure mental health support"}
          </p>
        </div>

        {/* Error Alert */}
        {errorMsg && (
          <div className="mb-5 flex items-start gap-2.5 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-900">
            <AlertCircle className="mt-0.5 size-4 shrink-0 text-rose-600" />
            <span className="break-words font-medium">{errorMsg}</span>
          </div>
        )}

        {/* Success Alert */}
        {successMsg && (
          <div className="mb-5 flex items-start gap-2.5 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900">
            <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" />
            <span className="break-words font-semibold">{successMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {!isLoginMode && (
            <div>
              <label htmlFor="mg-name" className="mb-1 block text-xs font-semibold text-slate-700">
                Full Name
              </label>
              <div className="relative">
                <User className="absolute left-3.5 top-3.5 size-4 text-slate-400" />
                <input
                  id="mg-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Muhammad Saqib"
                  className={fieldClass}
                  required={!isLoginMode}
                  disabled={isLoading}
                />
              </div>
            </div>
          )}

          <div>
            <label htmlFor="mg-email" className="mb-1 block text-xs font-semibold text-slate-700">
              Email Address
            </label>
            <div className="relative">
              <Mail className="absolute left-3.5 top-3.5 size-4 text-slate-400" />
              <input
                id="mg-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="user@example.com"
                className={fieldClass}
                required
                disabled={isLoading}
              />
            </div>
          </div>

          {!isLoginMode && (
            <label className="flex items-start gap-2 text-xs leading-relaxed text-slate-700">
              <input type="checkbox" checked={consentGiven} onChange={(e) => setConsentGiven(e.target.checked)} className="mt-0.5" />
              <span>I consent to MindGuard processing my sensitive text for non-clinical self-help support. I understand it is not medical care.</span>
            </label>
          )}

          <div>
            <label
              htmlFor="mg-password"
              className="mb-1 block text-xs font-semibold text-slate-700"
            >
              Password
            </label>
            <div className="relative">
              <Lock className="absolute left-3.5 top-3.5 size-4 text-slate-400" />
              <input
                id="mg-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className={fieldClass}
                required
                disabled={isLoading}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 py-3.5 text-sm font-semibold text-white shadow-xs transition-all hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-50 cursor-pointer"
          >
            {isLoading ? (
              <>
                <RefreshCw className="size-4 animate-spin" />
                <span>{isLoginMode ? "Signing In..." : "Registering Account..."}</span>
              </>
            ) : (
              <>
                <span>{isLoginMode ? "Sign In" : "Create Account"}</span>
                <ArrowRight className="size-4" />
              </>
            )}
          </button>
        </form>

        <div className="mt-6 text-center text-xs text-slate-600">
          {isLoginMode ? "Don't have an account yet?" : "Already have an account?"}{" "}
          <button
            type="button"
            onClick={() => {
              setIsLoginMode(!isLoginMode);
              setErrorMsg(null);
              setSuccessMsg(null);
            }}
            className="ml-1 font-bold text-indigo-600 hover:underline focus-visible:outline-none"
          >
            {isLoginMode ? "Register Now" : "Sign In"}
          </button>
        </div>
      </div>
    </div>
  );
}
