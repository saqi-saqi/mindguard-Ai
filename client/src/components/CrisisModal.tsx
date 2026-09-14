import { useEffect, useRef, useState } from "react";
import {
  PhoneCall,
  ShieldAlert,
  X,
  ExternalLink,
  Heart,
  AlertTriangle,
  Wind,
  Play,
  Pause,
  MessageSquare,
  Copy,
  Check,
  Info,
  ChevronDown,
  ChevronUp
} from "lucide-react";
import type { CrisisResources, Helpline, SafetyProfile, TrustedContact } from "./types";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  resources?: CrisisResources | null;
  trustedContact?: TrustedContact | null;
  safetyProfile?: SafetyProfile | null;
  mode?: "manual" | "detected";
  onSafetyStatus?: (outcome: "safe_for_now" | "urgent_help_requested") => void;
}

function formatSafeUrl(url?: string): string {
  if (!url) return "";
  const trimmed = url.trim();
  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) return trimmed;
  return `https://${trimmed}`;
}

function HelplineCard({
  h,
  tone,
  onNotify
}: {
  h: Helpline;
  tone: "rose" | "cyan" | "emerald";
  onNotify: (msg: string) => void;
}) {
  const [copied, setCopied] = useState(false);
  const name = h.name || h.organization || "Emergency Helpline";
  const contactText = (h.contact || h.contact_info || "").trim();
  const website = h.website;

  // Determine if pure website directory
  const isWebOnly = contactText.startsWith("http") || (!contactText.match(/\d/) && !contactText.toLowerCase().includes("text"));
  const webUrl = formatSafeUrl(website || (contactText.startsWith("http") ? contactText : undefined));

  // Extract phone numbers and text lines
  const hasTextSupport = contactText.toLowerCase().includes("text");
  
  // Extract primary dialable phone digits
  let primaryPhoneDigits = "";
  let primaryPhoneDisplay = "";
  let textCode = "";
  let textKeyword = "HOME";

  if (!isWebOnly) {
    if (contactText.includes("/")) {
      const parts = contactText.split("/");
      const phonePart = parts.find((p) => p.toLowerCase().includes("call") || !p.toLowerCase().includes("text")) || parts[0];
      primaryPhoneDisplay = phonePart.replace(/call/i, "").trim();
      primaryPhoneDigits = primaryPhoneDisplay.replace(/[^0-9+]/g, "");

      const textPart = parts.find((p) => p.toLowerCase().includes("text"));
      if (textPart) {
        const match = textPart.match(/text\s+([A-Za-z]+)\s+to\s+([0-9\-]+)/i);
        if (match) {
          textKeyword = match[1];
          textCode = match[2].replace(/[^0-9]/g, "");
        } else {
          textCode = textPart.replace(/[^0-9]/g, "");
        }
      }
    } else if (hasTextSupport) {
      const match = contactText.match(/text\s+([A-Za-z]+)\s+to\s+([0-9\-]+)/i);
      if (match) {
        textKeyword = match[1];
        textCode = match[2].replace(/[^0-9]/g, "");
      } else {
        textCode = contactText.replace(/[^0-9]/g, "");
      }
    } else {
      primaryPhoneDisplay = contactText;
      primaryPhoneDigits = contactText.replace(/[^0-9+]/g, "");
    }
  }

  const handleCopy = (text: string, label: string) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      onNotify(`Copied ${label} (${text}) to clipboard.`);
    }
  };

  const handleCall = (e: React.MouseEvent, phone: string, display: string) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(display || phone);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
    onNotify(`Dialing ${display || phone}... (Copied to clipboard. If on a computer, use your phone to dial).`);
    window.location.href = `tel:${phone}`;
  };

  const handleText = (e: React.MouseEvent, code: string, keyword: string) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(`Text ${keyword} to ${code}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
    onNotify(`Opening SMS to ${code}... (Copied 'Text ${keyword} to ${code}' to clipboard).`);
    window.location.href = `sms:${code}`;
  };

  return (
    <div
      className={`flex flex-col justify-between gap-2.5 rounded-2xl border bg-slate-900/90 p-3.5 transition-colors ${
        tone === "rose"
          ? "border-rose-500/40 hover:border-rose-500/70"
          : tone === "emerald"
            ? "border-emerald-500/40 hover:border-emerald-500/70"
            : "border-cyan-500/40 hover:border-cyan-500/70"
      }`}
    >
      <div className="min-w-0 space-y-0.5">
        <div className="flex items-center justify-between gap-2">
          <h4 className="break-words text-xs font-bold text-white font-heading">{name}</h4>
          <span className="shrink-0 rounded-full border border-emerald-500/40 bg-emerald-950/60 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-300">
            24/7 Verified
          </span>
        </div>
        {h.description && (
          <p className="break-words text-[11px] leading-relaxed text-slate-300 font-normal">{h.description}</p>
        )}
      </div>

      <div className="flex flex-col gap-1.5 pt-0.5">
        {/* Phone Call Action */}
        {primaryPhoneDigits && (
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={(e) => handleCall(e, primaryPhoneDigits, primaryPhoneDisplay)}
              className={`flex min-h-[38px] flex-1 items-center justify-center gap-2 rounded-xl px-3 py-1.5 text-xs font-bold text-white transition-colors focus-visible:outline-none focus-visible:ring-2 cursor-pointer ${
                tone === "rose"
                  ? "bg-rose-600 hover:bg-rose-500 focus-visible:ring-rose-300"
                  : tone === "emerald"
                    ? "bg-emerald-600 hover:bg-emerald-500 focus-visible:ring-emerald-300"
                    : "bg-cyan-600 hover:bg-cyan-500 focus-visible:ring-cyan-300"
              }`}
            >
              <PhoneCall className="size-3.5 shrink-0" />
              <span className="truncate">Call {primaryPhoneDisplay || primaryPhoneDigits}</span>
            </button>
            <button
              type="button"
              onClick={() => handleCopy(primaryPhoneDisplay || primaryPhoneDigits, name)}
              title="Copy phone number"
              aria-label={`Copy phone number for ${name}`}
              className="grid size-9 shrink-0 place-items-center rounded-xl border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 cursor-pointer"
            >
              {copied ? <Check className="size-3.5 text-emerald-400" /> : <Copy className="size-3.5" />}
            </button>
          </div>
        )}

        {/* Text / SMS Action */}
        {hasTextSupport && textCode && (
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={(e) => handleText(e, textCode, textKeyword)}
              className="flex min-h-[36px] flex-1 items-center justify-center gap-2 rounded-xl bg-purple-600 px-3 py-1.5 text-xs font-bold text-white transition-colors hover:bg-purple-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-300 cursor-pointer"
            >
              <MessageSquare className="size-3.5 shrink-0" />
              <span className="truncate">Text {textKeyword} to {textCode}</span>
            </button>
            <button
              type="button"
              onClick={() => handleCopy(`Text ${textKeyword} to ${textCode}`, name)}
              title="Copy SMS shortcode"
              aria-label={`Copy SMS shortcode for ${name}`}
              className="grid size-9 shrink-0 place-items-center rounded-xl border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 cursor-pointer"
            >
              {copied ? <Check className="size-3.5 text-emerald-400" /> : <Copy className="size-3.5" />}
            </button>
          </div>
        )}

        {/* Official Website / Directory Link */}
        {webUrl && (
          <a
            href={webUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex min-h-[34px] w-full items-center justify-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800/80 px-2.5 py-1 text-[11px] font-semibold text-slate-200 hover:bg-slate-700 hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 cursor-pointer"
          >
            <ExternalLink className="size-3 shrink-0 text-cyan-400" />
            <span>{isWebOnly ? "Open support website" : "Official Website & Resources"}</span>
          </a>
        )}
      </div>
    </div>
  );
}

export default function CrisisModal({ isOpen, onClose, resources, trustedContact, safetyProfile, mode = "manual", onSafetyStatus }: Props) {
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);

  const [notification, setNotification] = useState<string | null>(null);
  const [showFullDirectory, setShowFullDirectory] = useState(false);

  // Optional Breathing Assistant inside Modal (secondary tool)
  const [showBreathing, setShowBreathing] = useState(false);
  const [breathingActive, setBreathingActive] = useState(false);
  const [breathingPhase, setBreathingPhase] = useState<"Inhale" | "Hold" | "Exhale">("Inhale");
  const [breathingCount, setBreathingCount] = useState(4);

  const showNotification = (msg: string) => {
    setNotification(msg);
    setTimeout(() => {
      setNotification((prev) => (prev === msg ? null : prev));
    }, 4500);
  };

  const handleQuickCall = (e: React.MouseEvent, phoneDigits: string, label: string) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(phoneDigits);
    }
    showNotification(`Dialing ${phoneDigits}... (Copied to clipboard. If on a computer, use your phone to dial).`);
    window.location.href = `tel:${phoneDigits}`;
  };

  const handleQuickCopy = (phoneDigits: string, label: string) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(phoneDigits);
      showNotification(`Copied ${label} (${phoneDigits}) to clipboard.`);
    }
  };

  const handleQuickText = (phoneDigits: string, label: string) => {
    const message = "I need support right now. Please call me or stay with me if you can.";
    if (navigator.clipboard) navigator.clipboard.writeText(message);
    showNotification(`Opening a message to ${label}. The message is copied in case your device does not open SMS.`);
    window.location.href = `sms:${phoneDigits}?body=${encodeURIComponent(message)}`;
  };

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
        organization: "Umang Pakistan",
        contact: "0311-7786264",
        website: "https://www.umangpakistan.org",
        description: "Certified clinical psychologists offering 24/7 free emotional crisis counseling.",
      },
      {
        name: "Rozan Emotional Support Line",
        organization: "Rozan",
        contact: "0800-22444",
        website: "https://rozan.org",
        description: "Toll-free emotional health and trauma counseling support.",
      },
      {
        name: "Child Protection Bureau Helpline (CPWB)",
        organization: "CPWB Punjab",
        contact: "1121",
        website: "https://cpwb.punjab.gov.pk",
        description: "Government toll-free 24/7 crisis helpline for minors and youth in distress.",
      },
      {
        name: "Madadgaar National Helpline",
        organization: "Madadgaar",
        contact: "1098 / 021-35150075",
        website: "http://madadgaar.org",
        description: "Pakistan's first national crisis helpline for children, youth, and women.",
      },
      {
        name: "Taskeen Health Initiative",
        organization: "Taskeen",
        contact: "0316-8275336",
        website: "https://taskeen.org",
        description: "Free mental health support and clinical navigation.",
      },
    ],
  };

  // Primary mental health line for acute 3-action triage (Umang in PK)
  const primaryMentalHealthLine = defaultHelplines.pakistan?.[0] || {
    name: "Umang Pakistan Mental Health Helpline",
    contact: "0311-7786264",
    description: "Certified clinical psychologists offering 24/7 free emotional crisis counseling."
  };

  // Auxiliary resources for progressive disclosure directory
  const auxiliaryPakistanLines = (defaultHelplines.pakistan || []).slice(1);
  const totalDirectoryCount = auxiliaryPakistanLines.length;

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
      <div className="relative my-auto flex w-full max-w-xl max-h-[92vh] flex-col overflow-hidden rounded-3xl border border-rose-500/40 bg-slate-900 p-4 sm:p-6 shadow-2xl">
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
        <div className="relative mb-3 flex items-center gap-3 pr-10 shrink-0">
          <div className="grid size-10 shrink-0 place-items-center rounded-2xl border border-rose-500/40 bg-rose-500/20 text-rose-300">
            <ShieldAlert className="size-5" />
          </div>
          <div className="min-w-0">
            <div className="mb-0.5 inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-rose-300">
              <Heart className="size-3 fill-current text-rose-400" /> Immediate Safety Support
            </div>
            <h2 id="crisis-modal-title" className="text-lg font-bold text-white font-heading sm:text-xl">
              You Are Not Alone
            </h2>
          </div>
        </div>

        {/* Live Notification / Feedback Toast */}
        {notification && (
          <div className="fade-in mb-3 flex items-center gap-2 rounded-xl border border-emerald-500/50 bg-emerald-950/80 px-3.5 py-2 text-xs font-semibold text-emerald-200 shadow-md">
            <Info className="size-4 shrink-0 text-emerald-400" />
            <span className="break-words leading-relaxed">{notification}</span>
          </div>
        )}

        {/* Safety Notice Section */}
        <div
          id="crisis-modal-desc"
          className="relative mb-3 shrink-0 space-y-1 rounded-xl border border-rose-500/30 bg-slate-950/80 p-3 text-xs leading-relaxed text-slate-200"
        >
          <p className="break-words font-normal text-[11px] sm:text-xs">
            {mode === "detected"
              ? "MindGuard noticed language indicating severe distress. Please connect directly with live crisis support right away."
              : "If you may harm yourself or are in immediate physical danger, connect directly with one of these emergency options now."}
          </p>
          <p className="flex items-start gap-1.5 border-t border-rose-500/20 pt-1.5 text-[10px] sm:text-[11px] font-semibold text-rose-200">
            <AlertTriangle className="mt-0.5 size-3 shrink-0 text-amber-400" />
            <span>
              MindGuard is an automated AI tool and never contacts emergency services or personal contacts automatically.
            </span>
          </p>
        </div>

        {/* PRIMARY ACUTE TRIAGE: MAXIMUM 3 CORE ACTIONS (Hick's Law Optimization) */}
        <div className="relative min-h-0 flex-1 overflow-y-auto space-y-2.5 pr-1 pb-2">
          {/* ACTION 1: IMMEDIATE EMERGENCY RESCUE */}
          <div className="rounded-2xl border-2 border-rose-500 bg-rose-950/60 p-3 shadow-lg">
            <div className="flex items-center justify-between gap-2 mb-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-rose-300 flex items-center gap-1.5">
                <ShieldAlert className="size-3.5 text-rose-400" /> 1. Emergency Dispatch
              </h3>
              <span className="text-[9px] font-bold uppercase bg-rose-600 text-white px-2 py-0.5 rounded-full">
                Immediate Response
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={(e) => handleQuickCall(e, "1122", "Pakistan Rescue 1122")}
                  className="flex min-h-[44px] flex-1 items-center justify-center gap-2 rounded-xl bg-rose-600 px-3 py-2 text-xs font-bold text-white shadow-md transition-colors hover:bg-rose-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-300 cursor-pointer"
                >
                  <PhoneCall className="size-4 shrink-0" />
                  <span>Call 1122 (Pakistan Rescue)</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleQuickCopy("1122", "Pakistan Rescue 1122")}
                  title="Copy 1122"
                  aria-label="Copy 1122 emergency number"
                  className="grid size-11 shrink-0 place-items-center rounded-xl border border-rose-400/40 bg-rose-900/60 text-rose-200 hover:bg-rose-800 hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-300 cursor-pointer"
                >
                  <Copy className="size-4" />
                </button>
              </div>

              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={(e) => handleQuickCall(e, "15", "Pakistan Police Emergency")}
                  className="flex min-h-[44px] flex-1 items-center justify-center gap-2 rounded-xl bg-rose-700 px-3 py-2 text-xs font-bold text-white shadow-md transition-colors hover:bg-rose-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-300 cursor-pointer"
                >
                  <PhoneCall className="size-4 shrink-0" />
                  <span>Call 15 (Police Emergency)</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleQuickCopy("15", "Pakistan Police Emergency")}
                  title="Copy 15"
                  aria-label="Copy 15 emergency number"
                  className="grid size-11 shrink-0 place-items-center rounded-xl border border-rose-400/40 bg-rose-900/60 text-rose-200 hover:bg-rose-800 hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-300 cursor-pointer"
                >
                  <Copy className="size-4" />
                </button>
              </div>
            </div>
          </div>

          {/* ACTION 2: DESIGNATED TRUSTED CONTACT (Personal Anchor) */}
          {trustedContact && trustedContact.phone && (
            <div className="rounded-2xl border border-emerald-500/50 bg-emerald-950/40 p-3 shadow-lg">
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <h3 className="text-xs font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
                  <Heart className="size-3.5 text-emerald-400" /> 2. Designated Personal Anchor
                </h3>
                <span className="text-[9px] font-semibold text-emerald-300">Personal Support</span>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-bold text-white font-heading">{trustedContact.name}</p>
                  <p className="text-[11px] text-emerald-200/80">{trustedContact.relationship || "Personal Contact"}</p>
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={(e) => handleQuickCall(e, trustedContact.phone.replace(/[^0-9+]/g, ""), trustedContact.name)}
                    className="flex min-h-[40px] items-center gap-2 rounded-xl bg-emerald-600 px-3.5 py-1.5 text-xs font-bold text-white transition-colors hover:bg-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 cursor-pointer"
                  >
                    <PhoneCall className="size-3.5 shrink-0" />
                    <span>Call {trustedContact.name} ({trustedContact.phone})</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleQuickText(trustedContact.phone.replace(/[^0-9+]/g, ""), trustedContact.name)}
                    aria-label={`Text ${trustedContact.name} for support`}
                    className="grid size-10 shrink-0 place-items-center rounded-xl border border-emerald-500/40 bg-emerald-900/60 text-emerald-200 hover:bg-emerald-800 hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 cursor-pointer"
                  >
                    <MessageSquare className="size-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleQuickCopy(trustedContact.phone, trustedContact.name)}
                    title={`Copy ${trustedContact.name}'s phone number`}
                    aria-label={`Copy ${trustedContact.name}'s phone number`}
                    className="grid size-10 shrink-0 place-items-center rounded-xl border border-emerald-500/40 bg-emerald-900/60 text-emerald-200 hover:bg-emerald-800 hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 cursor-pointer"
                  >
                    <Copy className="size-3.5" />
                  </button>
                </div>
              </div>
            </div>
          )}

          {safetyProfile?.emergency_actions_consent && safetyProfile.preferred_hospital_phone && (
            <div className="rounded-2xl border border-indigo-500/50 bg-indigo-950/30 p-3 shadow-lg">
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-300 flex items-center gap-1.5">
                  <ShieldAlert className="size-3.5 text-indigo-400" /> Preferred Hospital
                </h3>
                <span className="text-[9px] font-semibold text-indigo-200">You choose when to call</span>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div><p className="text-sm font-bold text-white font-heading">{safetyProfile.preferred_hospital_name || "Saved hospital"}</p><p className="text-[11px] text-indigo-200/80">{safetyProfile.city_or_district || "Pakistan"}</p></div>
                <button type="button" onClick={(e) => handleQuickCall(e, safetyProfile.preferred_hospital_phone.replace(/[^0-9+]/g, ""), safetyProfile.preferred_hospital_name || "saved hospital")} className="flex min-h-[40px] items-center gap-2 rounded-xl bg-indigo-600 px-3.5 py-1.5 text-xs font-bold text-white transition-colors hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 cursor-pointer"><PhoneCall className="size-3.5 shrink-0" /><span>Call hospital</span></button>
              </div>
            </div>
          )}

          {/* ACTION 3: PRIMARY 24/7 MENTAL HEALTH LINE (Umang Pakistan) */}
          <div className="rounded-2xl border border-rose-500/40 bg-slate-900/90 p-3 shadow-md">
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <h3 className="text-xs font-bold uppercase tracking-wider text-rose-300 flex items-center gap-1.5">
                <Heart className="size-3.5 text-rose-400" /> {trustedContact?.phone ? "3." : "2."} Primary 24/7 Mental Health Line
              </h3>
              <span className="shrink-0 rounded-full border border-emerald-500/40 bg-emerald-950/60 px-2 py-0.5 text-[9px] font-semibold text-emerald-300">
                Verified 24/7
              </span>
            </div>
            <p className="text-[11px] text-slate-300 mb-2">{primaryMentalHealthLine.description}</p>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={(e) =>
                  handleQuickCall(
                    e,
                    (primaryMentalHealthLine.contact || "").replace(/[^0-9+]/g, ""),
                    primaryMentalHealthLine.name || "Umang Pakistan"
                  )
                }
                className="flex min-h-[42px] flex-1 items-center justify-center gap-2 rounded-xl bg-rose-600 px-3.5 py-2 text-xs font-bold text-white transition-colors hover:bg-rose-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-300 cursor-pointer"
              >
                <PhoneCall className="size-4 shrink-0" />
                <span>Call {primaryMentalHealthLine.name} ({primaryMentalHealthLine.contact})</span>
              </button>
              <button
                type="button"
                onClick={() =>
                  handleQuickCopy(
                    primaryMentalHealthLine.contact || "",
                    primaryMentalHealthLine.name || "Umang Pakistan"
                  )
                }
                title="Copy phone number"
                aria-label={`Copy phone number for ${primaryMentalHealthLine.name}`}
                className="grid size-10 shrink-0 place-items-center rounded-xl border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 cursor-pointer"
              >
                <Copy className="size-4" />
              </button>
            </div>
          </div>

          {/* PROGRESSIVE DISCLOSURE: PAKISTAN SUPPORT DIRECTORY */}
          <div className="rounded-2xl border border-slate-700/80 bg-slate-900/60 p-3">
            <button
              type="button"
              onClick={() => setShowFullDirectory(!showFullDirectory)}
              className="flex w-full items-center justify-between text-left text-xs font-bold text-slate-200 hover:text-white transition-colors cursor-pointer focus-visible:outline-none"
            >
              <div className="flex items-center gap-2">
                <span>
                  {showFullDirectory
                    ? "Hide Pakistan Support Directory"
                    : `View More Pakistan Helplines (${totalDirectoryCount} resources)`}
                </span>
              </div>
              {showFullDirectory ? (
                <ChevronUp className="size-4 text-slate-400" />
              ) : (
                <ChevronDown className="size-4 text-slate-400" />
              )}
            </button>

            {showFullDirectory && (
              <div className="mt-3 space-y-3 border-t border-slate-800 pt-3 fade-in">
                {/* Auxiliary Pakistan Helplines */}
                {auxiliaryPakistanLines.length > 0 && (
                  <div>
                    <h4 className="mb-2 text-[10px] font-bold uppercase tracking-wider text-rose-400">
                      Additional National Helplines (Pakistan)
                    </h4>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      {auxiliaryPakistanLines.map((h, i) => (
                        <HelplineCard key={i} h={h} tone="rose" onNotify={showNotification} />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
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
                  aria-label={breathingActive ? "Pause breathing exercise" : "Start breathing exercise"}
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
