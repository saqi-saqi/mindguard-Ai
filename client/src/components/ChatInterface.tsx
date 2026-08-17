import React, { useState, useRef, useEffect } from "react";
import {
  Send,
  Bot,
  User,
  Sparkles,
  RefreshCw,
  Wind,
  AlertCircle,
  HeartHandshake,
  Trash2,
  ChevronDown,
  ChevronUp,
  X,
  ShieldAlert,
  RotateCcw
} from "lucide-react";
import type { ChatMessage, CrisisResources, MoodLog, MindUser } from "./types";

const API_BASE_URL = "/api/chat";
const MAX_INPUT_LENGTH = 2000;

// Format raw model strings into friendly title case
const formatFriendlyLabel = (str?: string) => {
  if (!str) return "";
  return str
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
};

// Render markdown bold text and clean line breaks safely
const renderFormattedText = (text: string) => {
  if (!text) return null;
  const lines = text.split("\n");
  return lines.map((line, lineIdx) => {
    const parts = line.split(/(\*\*.*?\*\*)/g);
    const lineContent = parts.map((part, i) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return (
          <strong key={i} className="rounded bg-indigo-50/90 px-1 font-semibold text-slate-900">
            {part.slice(2, -2)}
          </strong>
        );
      }
      return part;
    });

    return (
      <React.Fragment key={lineIdx}>
        {lineContent}
        {lineIdx < lines.length - 1 && <br />}
      </React.Fragment>
    );
  });
};

function AnalysisBadges({ msg }: { msg: ChatMessage }) {
  const [showDetails, setShowDetails] = useState(false);

  if (msg.risk_level === "HIGH_CRISIS") {
    return (
      <div className="flex items-center gap-2 pt-2 px-1">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-rose-300 bg-rose-100 px-2.5 py-0.5 text-xs font-semibold text-rose-900 shadow-2xs">
          🚨 Crisis Protocol Active
        </span>
        <time className="text-xs text-slate-500">{msg.timestamp}</time>
      </div>
    );
  }

  const friendlyIntent = msg.intent ? formatFriendlyLabel(msg.intent) : null;
  const friendlyEmotion = msg.emotion ? formatFriendlyLabel(msg.emotion) : null;

  return (
    <div className="pt-2 px-1 text-xs text-slate-500">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setShowDetails(!showDetails)}
          aria-expanded={showDetails}
          aria-controls={`insight-${msg.id}`}
          className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-200/80 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 cursor-pointer"
        >
          <span>Possible emotional tone</span>
          {showDetails ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
        </button>
        {msg.sentiment && (
          <span className="inline-flex items-center gap-1 rounded-full border border-slate-200/90 bg-slate-50 px-2 py-0.5 text-xs font-medium text-slate-600">
            {msg.sentiment === "POSITIVE"
              ? "🟢 Possible tone · Positive"
              : msg.sentiment === "NEGATIVE"
                ? "🔴 Possible tone · Distressed"
                : "⚪ Possible tone · Neutral"}
          </span>
        )}
        <time className="ml-auto text-xs text-slate-500">{msg.timestamp}</time>
      </div>

      {showDetails && (
        <div id={`insight-${msg.id}`} className="mt-2 flex flex-col gap-1.5 rounded-xl border border-slate-200/90 bg-slate-50 p-2.5 text-xs text-slate-700 fade-in">
          <p className="text-[11px] text-slate-500 italic">
            Automated AI inference for self-reflection. Not a clinical psychological assessment or diagnosis.
          </p>
          <div className="flex flex-wrap items-center gap-2 pt-0.5">
            {friendlyIntent && (
              <span className="rounded-lg border border-indigo-200/80 bg-indigo-50/80 px-2.5 py-0.5 font-medium text-indigo-900">
                Topic focus: {friendlyIntent}
              </span>
            )}
            {friendlyEmotion && (
              <span className="rounded-lg border border-purple-200/80 bg-purple-50/80 px-2.5 py-0.5 font-medium text-purple-900">
                Inferred tone: {friendlyEmotion}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

interface ChatInterfaceProps {
  user?: MindUser | null;
  token?: string;
  initialMessages?: ChatMessage[];
  onOpenCrisisModal: (resources?: CrisisResources | null, mode?: "manual" | "detected") => void;
  onRecordMood: (log: MoodLog) => void;
  onWipePersonalData?: () => void;
}

export default function ChatInterface({
  user,
  token,
  initialMessages = [],
  onOpenCrisisModal,
  onRecordMood,
  onWipePersonalData
}: ChatInterfaceProps) {
  const defaultWelcome: ChatMessage = {
    id: "welcome",
    sender: "bot",
    text: "Hello! I am MindGuard, your automated AI mental health companion. I am here to offer empathetic listening, grounding techniques, and supportive exercises. How are you feeling today?",
    timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    intent: "GREETING OR CASUAL CHAT",
    emotion: "NEUTRAL",
    sentiment: "POSITIVE",
  };

  const [messages, setMessages] = useState<ChatMessage[]>([defaultWelcome]);
  const [inputText, setInputText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [lastFailedText, setLastFailedText] = useState<string | null>(null);
  const [liveAnnouncement, setLiveAnnouncement] = useState("");
  const [activeBreathing, setActiveBreathing] = useState(false);
  const [breathingCount, setBreathingCount] = useState(4);
  const [breathingPhase, setBreathingPhase] = useState<"Inhale" | "Hold" | "Exhale">("Inhale");
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [dismissedEmergencyBanner, setDismissedEmergencyBanner] = useState(false);

  const hasElevatedRisk = messages.some(
    (m) => m.risk_level === "HIGH_CRISIS" || m.risk_level === "ELEVATED_DISTRESS"
  );

  const clearedRef = useRef(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Sync initial historical messages from DB when authenticated
  useEffect(() => {
    if (clearedRef.current) return;
    if (initialMessages && initialMessages.length > 0) {
      setMessages([defaultWelcome, ...initialMessages]);
    }
  }, [initialMessages]);

  const scrollToBottom = () => {
    if (typeof messagesEndRef.current?.scrollIntoView === "function") {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  // Auto-resize the composer textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [inputText]);

  // Guided 4-7-8 Breathing Timer with reduced-motion awareness
  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | undefined;
    if (activeBreathing) {
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
  }, [activeBreathing, breathingPhase]);

  const handleSendMessage = async (textToSend?: string) => {
    const query = (textToSend || inputText).trim();
    if (!query || isLoading) return;

    if (query.length > MAX_INPUT_LENGTH) {
      setApiError(`Message exceeds maximum length of ${MAX_INPUT_LENGTH} characters.`);
      return;
    }

    setApiError(null);
    setLastFailedText(null);
    const userMsgId = Date.now().toString();
    const userMsg: ChatMessage = {
      id: userMsgId,
      sender: "user",
      text: query,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setInputText("");
    setIsLoading(true);

    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const response = await fetch(API_BASE_URL, {
        method: "POST",
        headers,
        body: JSON.stringify({ message: query, session_id: activeSessionId }),
      });

      let resData: any = null;
      try {
        resData = await response.json();
      } catch {
        if (!response.ok) {
          throw new Error(`Server error (${response.status}): Backend service is offline or unreachable.`);
        }
        throw new Error("Invalid or empty response received from server.");
      }
      const data = resData.data || resData;

      if (resData.success !== false && data.reply) {
        if (data.session_id) setActiveSessionId(data.session_id);
        const botMsg: ChatMessage = {
          id: (Date.now() + 1).toString(),
          sender: "bot",
          text: data.reply,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          risk_level: data.risk_level,
          intent: data.intent,
          intent_confidence: data.intent_confidence,
          emotion: data.emotion,
          sentiment: data.sentiment,
          grounding_exercise: data.grounding_exercise,
        };

        setMessages((prev) => [...prev, botMsg]);
        setLiveAnnouncement(`New message from MindGuard: ${data.reply}`);

        if (data.risk_level === "HIGH_CRISIS") {
          onOpenCrisisModal(data.emergency_resources, "detected");
        }
      } else {
        const errObj = resData.error || {};
        throw new Error(errObj.message || data.message || "Unable to process request.");
      }
    } catch (err) {
      console.error("API Error:", err);
      const errMsg = (err as Error).message || "Unable to connect to backend server.";
      setApiError(errMsg);
      setLastFailedText(query);
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          sender: "bot",
          text: "I encountered a connection error reaching the backend server. Please verify that the Flask service is running on port 5000.",
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          isError: true,
        },
      ]);
      setLiveAnnouncement("Assistant response failed due to network error.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSendMessage();
    }
  };

  const handleRetry = () => {
    if (lastFailedText) {
      void handleSendMessage(lastFailedText);
    }
  };

  const handleClearHistory = () => {
    clearedRef.current = true;
    if (onWipePersonalData) {
      onWipePersonalData();
    }
    setMessages([defaultWelcome]);
    setActiveSessionId(null);
  };

  // Vetted, reviewed suggestion bank for safe user prompts
  const quickPills = [
    "I am feeling anxious about my upcoming exam",
    "I'm having trouble sleeping and feel exhausted",
    "I've been feeling lonely and down lately",
    "Could you guide me through a calming breathing exercise?",
  ];

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden bg-slate-50 font-sans">
      {/* Screen Reader Live Region for Assistant Announcements */}
      <div role="status" aria-live="polite" className="sr-only">
        {liveAnnouncement}
      </div>

      {/* Header */}
      <header className="z-10 grid shrink-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-slate-200/90 bg-white px-4 py-3 sm:px-6 shadow-2xs">
        <div className="flex min-w-0 items-center gap-3">
          <div className="relative shrink-0">
            <div className="grid size-10 place-items-center rounded-xl bg-indigo-600 text-white shadow-xs">
              <Bot className="size-5" />
            </div>
            <span
              className="absolute bottom-0 right-0 size-2.5 rounded-full border-2 border-white bg-emerald-500"
              title="System Online"
            />
          </div>
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-2">
              <h1 className="truncate text-base font-bold text-slate-900 font-heading">
                MindGuard Assistant
              </h1>
              <span className="hidden shrink-0 items-center rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-800 sm:inline-flex">
                Active
              </span>
            </div>
            <p className="truncate text-xs text-slate-600">Non-Clinical Mental Wellness Companion</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {user && (
            <button
              type="button"
              onClick={handleClearHistory}
              title="Delete chat and mood history"
              className="hidden sm:flex items-center gap-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 transition-colors hover:border-rose-300 hover:bg-rose-50 hover:text-rose-700 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400"
            >
              <Trash2 className="size-3.5 text-rose-600" />
              <span>Clear History</span>
            </button>
          )}

          {/* Urgent Help Button - Elevated emphasis when risk detected */}
          <button
            type="button"
            onClick={() => onOpenCrisisModal(null, "manual")}
            aria-label="Get urgent help and crisis resources"
            className={
              hasElevatedRisk
                ? "flex shrink-0 items-center gap-1.5 rounded-xl border border-rose-500 bg-rose-600 px-3.5 py-1.5 text-xs font-bold text-white shadow-xs transition-colors hover:bg-rose-700 animate-pulse focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 cursor-pointer"
                : "flex shrink-0 items-center gap-1.5 rounded-xl border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-800 shadow-2xs transition-colors hover:bg-rose-100 hover:text-rose-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400 cursor-pointer"
            }
          >
            <ShieldAlert className={hasElevatedRisk ? "size-4 shrink-0 text-rose-100" : "size-3.5 shrink-0 text-rose-600"} />
            <span className={hasElevatedRisk ? "font-bold" : "font-medium"}>Get urgent help</span>
          </button>

          {/* Guided 4-7-8 Breathing Toggle */}
          <button
            type="button"
            onClick={() => setActiveBreathing(!activeBreathing)}
            aria-label={activeBreathing ? "Stop breathing exercise" : "Start 4-7-8 breathing exercise"}
            aria-pressed={activeBreathing}
            className={`flex shrink-0 items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 cursor-pointer ${
              activeBreathing
                ? "border-indigo-300 bg-indigo-50 text-indigo-900 shadow-xs"
                : "border-slate-200 bg-slate-100 text-slate-700 hover:bg-slate-200/80 hover:text-slate-900"
            }`}
          >
            <Wind className="size-3.5 shrink-0 text-indigo-600" />
            <span className="hidden sm:inline">
              {activeBreathing ? "Stop Breathing" : "4-7-8 Breathing"}
            </span>
            <span className="sm:hidden">{activeBreathing ? "Stop" : "4-7-8"}</span>
          </button>
        </div>
      </header>

      {/* Guided 4-7-8 Breathing Banner */}
      {activeBreathing && (
        <div className="fade-in shrink-0 border-b border-indigo-200/90 bg-indigo-50/90 px-4 py-2.5 text-slate-900 sm:px-6">
          <div className="mx-auto flex w-full max-w-[780px] items-center justify-between gap-4">
            <div className="flex items-center gap-3.5 min-w-0">
              <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-indigo-600 font-bold text-white text-base shadow-xs">
                {breathingCount}
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-700">Guided Relaxation</span>
                  <span className="text-xs font-bold text-indigo-900 font-heading">• {breathingPhase}</span>
                </div>
                <p className="truncate text-xs text-slate-600 font-normal">
                  Inhale for 4s, hold for 7s, exhale slowly for 8s to release nervous tension.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setActiveBreathing(false)}
              className="rounded-lg p-1 text-slate-500 hover:bg-indigo-100 hover:text-slate-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 cursor-pointer"
              aria-label="Close breathing exercise banner"
            >
              <X className="size-4" />
            </button>
          </div>
        </div>
      )}

      {/* Messages Scroll Area */}
      <div
        className="min-h-0 flex-1 overflow-y-auto py-5"
        aria-label="Conversation history"
      >
        <div className="mx-auto w-full max-w-[780px] space-y-5 px-4 sm:px-6">
          {/* Welcome Card & Orientation (Compact, Clean, Non-clinical Scope) */}
          {messages.length === 1 && (
            <div className="mx-auto my-2.5 max-w-md rounded-2xl border border-indigo-100 bg-white p-3.5 text-center shadow-2xs fade-in">
              <div className="mx-auto mb-2 grid size-9 place-items-center rounded-xl bg-indigo-600 text-white shadow-xs">
                <HeartHandshake className="size-5" />
              </div>
              <h2 className="text-sm font-bold text-slate-900 font-heading">Welcome to MindGuard AI</h2>
              <p className="mt-1 text-xs text-slate-600 leading-normal font-normal">
                I’m here for supportive conversation, self-help coping strategies, and grounding exercises.
                Select a topic prompt below or write what is on your mind.
              </p>
            </div>
          )}

          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`fade-in flex w-full max-w-[95%] gap-3 sm:max-w-[85%] ${
                msg.sender === "user" ? "ml-auto flex-row-reverse" : ""
              }`}
            >
              <div
                className={`grid size-8 shrink-0 place-items-center rounded-lg text-xs font-bold shadow-2xs ${
                  msg.sender === "user"
                    ? "bg-indigo-600 text-white"
                    : "border border-slate-200/90 bg-white text-indigo-600"
                }`}
              >
                {msg.sender === "user" ? <User className="size-4" /> : <Bot className="size-4" />}
              </div>

              <div className="min-w-0 flex-1">
                <div
                  className={`rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-2xs ${
                    msg.sender === "user"
                      ? "rounded-tr-xs bg-indigo-600 text-white"
                      : msg.risk_level === "HIGH_CRISIS"
                        ? "rounded-tl-xs border border-rose-200 bg-rose-50 text-rose-900 font-medium"
                        : msg.isError
                          ? "rounded-tl-xs border border-amber-200 bg-amber-50 text-amber-900"
                          : "rounded-tl-xs border border-slate-200/90 bg-white text-slate-800"
                  }`}
                >
                  <div className="whitespace-pre-wrap break-words leading-relaxed font-normal">
                    {renderFormattedText(msg.text)}
                  </div>
                </div>

                {/* Grounding Exercise Card */}
                {msg.grounding_exercise && (
                  <div className="mt-2 rounded-xl border border-purple-200/80 bg-purple-50/80 p-3 text-xs text-purple-950 shadow-2xs">
                    <div className="mb-1 flex items-center gap-1.5 text-xs font-bold text-purple-900 font-heading">
                      <Sparkles className="size-3.5 shrink-0 text-purple-600" />
                      <span>Suggested Grounding Exercise</span>
                    </div>
                    <p className="break-words leading-relaxed font-normal">
                      {msg.grounding_exercise}
                    </p>
                  </div>
                )}

                {msg.sender === "bot" && (msg.intent || msg.sentiment) && (
                  <AnalysisBadges msg={msg} />
                )}
                {msg.sender === "bot" && !msg.intent && !msg.sentiment && (
                  <div className="px-1 pt-1 text-xs text-slate-500">{msg.timestamp}</div>
                )}
                {msg.sender === "user" && (
                  <div className="px-1 pt-1 text-right text-xs text-slate-500">
                    {msg.timestamp}
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Accessible Loading State */}
          {isLoading && (
            <div className="fade-in flex items-center gap-2.5 text-xs text-slate-600 font-medium" aria-busy="true">
              <div className="grid size-8 shrink-0 place-items-center rounded-lg border border-slate-200 bg-white text-indigo-600 shadow-2xs">
                <RefreshCw className="size-3.5 animate-spin" />
              </div>
              <div className="rounded-xl border border-slate-200/90 bg-white px-3.5 py-2.5 text-slate-700 shadow-2xs">
                Thinking and generating supportive response...
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Composer Section */}
      <div className="z-20 shrink-0 border-t border-slate-200/90 bg-white px-4 pt-2.5 pb-3 sm:px-6">
        <div className="mx-auto w-full max-w-[780px] space-y-2">
          {/* Conditional Urgent Safety Banner - only rendered during elevated distress / crisis detection */}
          {hasElevatedRisk && !dismissedEmergencyBanner && (
            <div className="flex items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs leading-relaxed text-rose-950 fade-in">
              <span className="min-w-0 flex-1">
                If you may be in physical danger or considering self-harm, please connect with crisis services immediately.
              </span>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  type="button"
                  onClick={() => onOpenCrisisModal(null, "manual")}
                  className="font-bold text-rose-800 underline hover:text-rose-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 cursor-pointer"
                >
                  Get help
                </button>
                <button
                  type="button"
                  onClick={() => setDismissedEmergencyBanner(true)}
                  aria-label="Dismiss safety banner"
                  className="grid size-6 place-items-center rounded-lg text-rose-700 hover:bg-rose-200/80 hover:text-rose-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 cursor-pointer"
                >
                  <X className="size-3.5" />
                </button>
              </div>
            </div>
          )}

          {/* API Error & Retry State */}
          {apiError && (
            <div className="flex items-start justify-between gap-2 rounded-xl border border-rose-200 bg-rose-50 p-2.5 text-xs text-rose-900">
              <div className="flex min-w-0 items-start gap-2">
                <AlertCircle className="mt-0.5 size-4 shrink-0 text-rose-600" />
                <span className="break-words font-medium">{apiError}</span>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {lastFailedText && (
                  <button
                    type="button"
                    onClick={handleRetry}
                    className="inline-flex items-center gap-1 rounded bg-rose-200 px-2 py-0.5 text-xs font-bold text-rose-900 hover:bg-rose-300 focus-visible:outline-none cursor-pointer"
                  >
                    <RotateCcw className="size-3" /> Retry
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setApiError(null)}
                  className="rounded px-1.5 text-xs font-bold text-slate-600 hover:text-slate-900 focus-visible:outline-none cursor-pointer"
                >
                  Dismiss
                </button>
              </div>
            </div>
          )}

          {/* Responsive Suggestions Container */}
          <div className="flex flex-wrap items-center gap-1.5 py-0.5">
            <span className="shrink-0 text-[10px] font-bold uppercase tracking-wider text-slate-500 mr-0.5">
              Suggestions:
            </span>
            {quickPills.map((pill, i) => (
              <button
                key={i}
                type="button"
                onClick={() => void handleSendMessage(pill)}
                disabled={isLoading}
                className="rounded-full border border-slate-200/90 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700 transition-all hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-50 cursor-pointer shadow-2xs"
              >
                {pill}
              </button>
            ))}
          </div>

          {/* Message Input Form */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void handleSendMessage();
            }}
            className="flex items-end gap-2 rounded-2xl border border-slate-300 bg-white p-2 shadow-xs transition-colors focus-within:border-indigo-600 focus-within:ring-2 focus-within:ring-indigo-100"
          >
            <label htmlFor="mindguard-composer" className="sr-only">
              Message MindGuard (Press Enter to send, Shift+Enter for new line)
            </label>
            <textarea
              id="mindguard-composer"
              ref={textareaRef}
              value={inputText}
              maxLength={MAX_INPUT_LENGTH}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              placeholder="Type your message... (Enter to send, Shift+Enter for new line)"
              className="max-h-28 min-h-[38px] flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-slate-900 placeholder:text-slate-500 focus:outline-none font-sans leading-relaxed"
              disabled={isLoading}
            />

            <button
              type="submit"
              disabled={!inputText.trim() || isLoading}
              aria-label="Send message"
              className="grid size-9 shrink-0 place-items-center rounded-xl bg-indigo-600 text-white shadow-xs transition-all hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400 cursor-pointer"
            >
              <Send className="size-4" />
            </button>
          </form>

          {/* Disclaimer Footer */}
          <div className="pt-0.5 text-center">
            <p className="text-[11px] leading-tight text-slate-500 font-normal">
              MindGuard is an automated self-help tool, not a clinical medical provider. For emergencies,
              contact <strong className="font-bold text-rose-700">1122 PK</strong> / <strong className="font-bold text-rose-700">988 US/CA</strong> or your local emergency hospital.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
