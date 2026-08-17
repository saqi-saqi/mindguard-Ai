import { useEffect, useRef, useState } from "react";
import { PhoneCall, ShieldAlert, X, ExternalLink, Heart, AlertTriangle, Wind, Play, Pause, CheckCircle2 } from "lucide-react";
import type { CrisisResources, Helpline, TrustedContact } from "./types";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  resources?: CrisisResources | null;
  trustedContact?: TrustedContact | null;
  mode?: "manual" | "detected";
  onSafetyStatus?: (outcome: "safe_for_now" | "urgent_help_requested") => void;
}

function HelplineCard({ h, tone }: { h: Helpline; tone: "rose" | "cyan" | "emerald" }) {
  const name = h.name || h.organization || "Emergency Helpline";
  const contactText = h.contact || h.contact_info || "";
  const website = h.website;
  const isWebLink = website || contactText.startsWith("http");
  const targetUrl = website || contactText;
  const isTextLine = contactText.toLowerCase().includes("text");
  const cleanPhone = contactText.replace(/[^0-9+]/g, "");

  const handleCallClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    if (!cleanPhone && !contactText) {
      e.preventDefault();
      return;
    }
  };

  return (
    <div
      className={`flex flex-col justify-between gap-2.5 rounded-2xl border bg-slate-900/90 p-4 transition-colors ${
        tone === "rose"
          ? "border-rose-500/40 hover:border-rose-500/70"
          : tone === "emerald"
            ? "border-emerald-500/40 hover:border-emerald-500/70"
            : "border-cyan-500/40 hover:border-cyan-500/70"
      }`}
    >
      <div className="min-w-0">
        <div className="flex items-center justify-between gap-2">
          <h4 className="break-words text-sm font-bold text-white font-heading">{name}</h4>
          <span className="shrink-0 rounded-full border border-emerald-500/40 bg-emerald-950/60 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
            Verified 24/7
          </span>
        </div>
        {h.description && (
          <p className="mt-1 break-words text-xs leading-relaxed text-slate-300 font-normal">{h.description}</p>
        )}
      </div>
      {isWebLink ? (
        <a
          href={targetUrl}
          target="_blank"
          rel="noreferrer"
          className="flex min-h-[44px] w-full items-center justify-center gap-2 rounded-xl border border-cyan-500/50 bg-cyan-600/30 px-3 py-2 text-xs font-bold text-cyan-100 hover:bg-cyan-600/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 cursor-pointer"
        >
          <ExternalLink className="size-4 shrink-0" />
          <span>Visit Official Directory</span>
        </a>
      ) : isTextLine ? (
        <a
          href={cleanPhone ? `sms:${cleanPhone}` : "#"}
          className="flex min-h-[44px] w-full items-center justify-center gap-2 rounded-xl bg-purple-600 px-3 py-2 text-xs font-bold text-white transition-colors hover:bg-purple-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-300 cursor-pointer"
        >
          <PhoneCall className="size-4 shrink-0" />
          <span className="break-all">{contactText}</span>
        </a>
      ) : (
        <a
          href={`tel:${cleanPhone || contactText}`}
          onClick={handleCallClick}
          className={`flex min-h-[44px] w-full items-center justify-center gap-2 rounded-xl px-3 py-2 text-xs font-bold text-white transition-colors focus-visible:outline-none focus-visible:ring-2 cursor-pointer ${
            tone === "rose"
              ? "bg-rose-600 hover:bg-rose-500 focus-visible:ring-rose-300"
              : tone === "emerald"
                ? "bg-emerald-600 hover:bg-emerald-500 focus-visible:ring-emerald-300"
                : "bg-cyan-600 hover:bg-cyan-500 focus-visible:ring-cyan-300"
          }`}
        >
          <PhoneCall className="size-4 shrink-0" />
          <span className="break-all">Call {contactText}</span>
        </a>
      )}
    </div>
  );
}

export default function CrisisModal({ isOpen, onClose, resources, trustedContact, mode = "manual", onSafetyStatus }: Props) {
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);

  // Optional Breathing Assistant inside Modal (secondary tool)
  const [showBreathing, setShowBreathing] = useState(false);
  const [breathingActive, setBreathingActive] = useState(false);
  const [breathingPhase, setBreathingPhase] = useState<"Inhale" | "Hold" | "Exhale">("Inhale");
  const [breathingCount, setBreathingCount] = useState(4);

  // Focus management, restoration, and keyboard trap
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

  // Optional breathing timer inside modal
  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | undefined;
    if (breathingActive) {
      timer = setInterval(() => {
        setBreathingCount((prev) => {
          if (prev <= 1) {
            if (breathingPhase === "Inhale") {
              setBreathingPhase("Hold");
              return 7;
            } else if (breathingPhase === "Hold") {
              setBreathingPhase("Exhale");
              return 8;
            } else {
              setBreathingPhase("Inhale");
              return 4;
            }
          }
          return prev - 1;
        });
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [breathingActive, breathingPhase]);

  if (!isOpen) return null;

  const defaultHelplines: CrisisResources = resources || {
    pakistan: [
      {
        name: "Umang Pakistan Mental Health Helpline",
        contact: "0311-7786264",
        description: "Certified clinical psychologists offering 24/7 free emotional crisis counseling.",
      },
      {
        name: "Rozan Emotional Support Line",
        contact: "0800-22444",
        description: "Toll-free emotional health and trauma counseling support.",
      },
      {
        name: "Taskeen Health Initiative",
        contact: "0316-8275336",
        description: "Free mental health support and clinical navigation.",
      },
    ],
    international: [
      {
        name: "Suicide & Crisis Lifeline (US & Canada)",
        contact: "988",
        description: "Free, confidential 24/7 call and text crisis line.",
      },
      {
        name: "Crisis Text Line",
        contact: "Text HOME to 741741",
        description: "Free 24/7 text support with trained crisis counselors.",
      },
      {
        name: "Find A Helpline (Global Directory)",
        contact: "https://findahelpline.com",
        description: "Confidential crisis lines in over 130 countries worldwide.",
      },
    ],
  };

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="crisis-modal-title"
      aria-describedby="crisis-modal-desc"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onSafetyStatus?.("safe_for_now");
          onClose();
        }
      }}
      className="fade-in fixed inset-0 z-[60] flex items-center justify-center overflow-y-auto bg-slate-950/90 p-3 backdrop-blur-md sm:p-4"
    >
      <div className="relative my-auto flex w-full max-w-2xl max-h-[92vh] flex-col overflow-hidden rounded-3xl border border-rose-500/40 bg-slate-900 p-4 sm:p-6 shadow-2xl">
        <div className="pointer-events-none absolute -right-24 -top-24 size-60 rounded-full bg-rose-500/20 blur-3xl" />

        <button
          ref={closeButtonRef}
          type="button"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onSafetyStatus?.("safe_for_now");
            onClose();
          }}
          aria-label="Close emergency modal and return to conversation"
          className="absolute right-4 top-4 z-50 grid size-10 place-items-center rounded-full border border-slate-700 bg-slate-800 text-slate-300 shadow-md transition-colors hover:bg-slate-700 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400 cursor-pointer"
        >
          <X className="size-5" />
        </button>

        {/* Header Section */}
        <div className="relative mb-3 flex items-center gap-3.5 pr-10 shrink-0">
          <div className="grid size-11 shrink-0 place-items-center rounded-2xl border border-rose-500/40 bg-rose-500/20 text-rose-300">
            <ShieldAlert className="size-6" />
          </div>
          <div className="min-w-0">
            <div className="mb-0.5 inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-rose-300">
              <Heart className="size-3 fill-current text-rose-400" /> Immediate Safety Support
            </div>
            <h2 id="crisis-modal-title" className="text-lg font-bold text-white font-heading sm:text-xl">
              You Are Not Alone
            </h2>
          </div>
        </div>

        {/* Safety Notice Section */}
        <div
          id="crisis-modal-desc"
          className="relative mb-3 shrink-0 space-y-1.5 rounded-xl border border-rose-500/30 bg-slate-950/80 p-3 text-xs leading-relaxed text-slate-200"
        >
          <p className="break-words font-normal">
            {mode === "detected"
              ? "MindGuard noticed language indicating you may be going through severe distress. Please connect directly with human crisis support right away."
              : "You requested urgent help. If you may harm yourself or are in immediate physical danger, use one of these services now."}
          </p>
          <p className="flex items-start gap-1.5 border-t border-rose-500/20 pt-1.5 text-[11px] font-semibold text-rose-200">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-400" />
            <span>
              MindGuard is an automated AI tool, not an emergency clinical service. MindGuard never contacts emergency services or your contacts automatically.
            </span>
          </p>
        </div>

        {/* LEVEL 1: IMMEDIATE EMERGENCY SERVICES (Always Visible Top Action) */}
        <div className="mb-3 shrink-0 rounded-2xl border-2 border-rose-500 bg-rose-950/60 p-3.5 shadow-lg">
          <div className="flex items-center justify-between gap-2 mb-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-rose-300 flex items-center gap-1.5">
              <ShieldAlert className="size-4 text-rose-400" /> Level 1: Immediate Emergency Services
            </h3>
            <span className="text-[10px] font-bold uppercase bg-rose-600 text-white px-2 py-0.5 rounded-full">
              Immediate Response
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <a
              href="tel:1122"
              className="flex min-h-[46px] items-center justify-center gap-2 rounded-xl bg-rose-600 px-4 py-2.5 text-xs font-bold text-white shadow-md transition-colors hover:bg-rose-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-300 cursor-pointer"
            >
              <PhoneCall className="size-4 shrink-0" />
              <span>Call 1122 (Pakistan Rescue)</span>
            </a>
            <a
              href="tel:988"
              className="flex min-h-[46px] items-center justify-center gap-2 rounded-xl bg-rose-700 px-4 py-2.5 text-xs font-bold text-white shadow-md transition-colors hover:bg-rose-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-300 cursor-pointer"
            >
              <PhoneCall className="size-4 shrink-0" />
              <span>Call 988 (US / Canada Lifeline)</span>
            </a>
          </div>
        </div>

        {/* Scrollable Resource List Section */}
        <div className="relative min-h-0 flex-1 overflow-y-auto space-y-3.5 pr-1 pb-4">
          {/* LEVEL 2: DESIGNATED TRUSTED CONTACT */}
          {trustedContact && trustedContact.phone && (
            <div className="rounded-2xl border border-emerald-500/50 bg-emerald-950/40 p-3.5 shadow-lg">
              <h3 className="mb-1 text-[11px] font-bold uppercase tracking-wider text-emerald-400">
                Designated Personal Trusted Contact
              </h3>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-bold text-white font-heading">{trustedContact.name}</p>
                  <p className="text-xs text-emerald-200/80">{trustedContact.relationship || "Personal Contact"}</p>
                </div>
                <a
                  href={`tel:${trustedContact.phone.replace(/[^0-9+]/g, "")}`}
                  className="flex min-h-[42px] items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-xs font-bold text-white transition-colors hover:bg-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 cursor-pointer"
                >
                  <PhoneCall className="size-4 shrink-0" />
                  <span>Call {trustedContact.name}</span>
                </a>
              </div>
            </div>
          )}

          {/* LEVEL 3: 24/7 REGIONAL CRISIS HELPLINES */}
          <div>
            <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-rose-400">
              National Crisis Helplines (Pakistan)
            </h3>
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              {defaultHelplines.pakistan?.map((h, i) => (
                <HelplineCard key={i} h={h} tone="rose" />
              ))}
            </div>
          </div>

          {/* LEVEL 4: INTERNATIONAL HELPLINES & FINDER */}
          <div>
            <h3 className="mb-2 pt-1 text-[11px] font-bold uppercase tracking-wider text-cyan-400">
              International Support &amp; Global Directory
            </h3>
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              {defaultHelplines.international?.map((h, i) => (
                <HelplineCard key={i} h={h} tone="cyan" />
              ))}
            </div>
          </div>

          {/* OPTIONAL GROUNDING / BREATHING ACCORDION (Non-obstructive) */}
          <div className="rounded-2xl border border-indigo-500/30 bg-indigo-950/30 p-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-bold text-indigo-300">
                <Wind className="size-4 text-indigo-400" />
                <span>Need a moment to slow down? (Optional Breathing)</span>
              </div>
              <button
                type="button"
                onClick={() => setShowBreathing(!showBreathing)}
                className="text-xs font-bold text-indigo-300 hover:text-white underline cursor-pointer focus-visible:outline-none"
              >
                {showBreathing ? "Hide" : "Open 4-7-8 Tool"}
              </button>
            </div>

            {showBreathing && (
              <div className="mt-3 flex items-center justify-between gap-4 rounded-xl bg-indigo-900/40 p-3 text-xs text-indigo-200">
                <div className="flex items-center gap-3">
                  <div className="grid size-9 place-items-center rounded-lg bg-indigo-600 font-bold text-white">
                    {breathingCount}
                  </div>
                  <div>
                    <p className="font-bold text-white">{breathingPhase}</p>
                    <p className="text-[11px] text-indigo-300">4s Inhale, 7s Hold, 8s Exhale</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setBreathingActive(!breathingActive)}
                  className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-indigo-500 cursor-pointer"
                >
                  {breathingActive ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
                  <span>{breathingActive ? "Pause" : "Start"}</span>
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Sticky Footer Section */}
        <div className="relative mt-2 flex shrink-0 items-center justify-between gap-3 border-t border-slate-800 pt-3 text-xs text-slate-400">
          <span className="min-w-0 break-words text-[11px] font-medium text-slate-400">
            Helpline information is verified and remains available at any time.
          </span>
          <button
            type="button"
            onClick={() => {
              onSafetyStatus?.("safe_for_now");
              onClose();
            }}
            className="shrink-0 rounded-xl bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 transition-colors hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 cursor-pointer"
          >
            I'm safe for now — return to chat
          </button>
        </div>
      </div>
    </div>
  );
}
