import React, { useEffect, useMemo, useRef, useState } from "react";
import { Activity, Plus, Trash2, Calendar, Info, BarChart3, TrendingUp, CheckCircle2, AlertCircle, MessageCircle, Compass } from "lucide-react";
import type { MoodLog } from "./types";

interface Props {
  moodLogs?: MoodLog[];
  onClearLogs?: () => void;
  token?: string;
  onMoodCreated?: (log: MoodLog) => void;
  onStartChat?: () => void;
}

const COMMON_TAGS = ["Exam", "Sleep", "Exercise", "Work", "Family", "Social", "Study", "Relaxation"];

export default function AnalyticsDashboard({ moodLogs = [], onClearLogs, token, onMoodCreated, onStartChat }: Props) {
  const [period, setPeriod] = useState("monthly");
  const [logs, setLogs] = useState<MoodLog[]>(moodLogs);
  const [score, setScore] = useState(5);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [customTagsList, setCustomTagsList] = useState<string[]>([]);
  const [customTag, setCustomTag] = useState("");
  const [notes, setNotes] = useState("");
  const [statusMessage, setStatusMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const lastSubmitRef = useRef<number>(0);
  const messageTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const formRef = useRef<HTMLFormElement | null>(null);
  const sliderRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    setLogs(moodLogs);
  }, [moodLogs]);

  useEffect(() => {
    if (!token) return;
    fetch(`/api/analytics?period=${period}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(async (r) => (r.ok ? r.json().catch(() => null) : null))
      .then((data) => {
        if (data && data.success !== false && data.data) {
          setLogs(data.data.mood_logs || []);
        }
      })
      .catch(() => showMessage("Could not load analytics summary.", "error"));
  }, [period, token]);

  const reflection = useMemo(() => {
    const datedLogs = [...logs].sort((a, b) => {
      const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
      const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
      return aTime - bTime;
    });
    const total = logs.length;
    const recent = datedLogs.slice(-Math.min(7, total));
    const recentAverage = recent.length
      ? recent.reduce((sum, log) => sum + Number(log.score || 0), 0) / recent.length
      : null;

    let previousAverage: number | null = null;
    let change: number | null = null;
    if (total >= 4) {
      const windowSize = Math.min(5, Math.floor(total / 2));
      const currentWindow = datedLogs.slice(-windowSize);
      const priorWindow = datedLogs.slice(-windowSize * 2, -windowSize);
      if (currentWindow.length > 0 && priorWindow.length > 0) {
        const curAvg = currentWindow.reduce((sum, log) => sum + Number(log.score || 0), 0) / currentWindow.length;
        const prevAvg = priorWindow.reduce((sum, log) => sum + Number(log.score || 0), 0) / priorWindow.length;
        previousAverage = prevAvg;
        change = curAvg - prevAvg;
      }
    }

    const scores = recent.map((log) => Number(log.score || 0));
    const tagStats: Record<string, { count: number; total: number }> = {};
    datedLogs.forEach((log) => (log.tags || []).forEach((rawTag) => {
      const tag = rawTag.trim();
      if (!tag) return;
      const key = tag.toLowerCase();
      if (!tagStats[key]) tagStats[key] = { count: 0, total: 0 };
      tagStats[key].count += 1;
      tagStats[key].total += Number(log.score || 0);
    }));
    const contexts = Object.entries(tagStats)
      .filter(([, value]) => value.count >= 2)
      .map(([tag, value]) => ({ tag, count: value.count, average: value.total / value.count }))
      .sort((a, b) => b.count - a.count || a.average - b.average)
      .slice(0, 3);

    return {
      total,
      recent,
      recentAverage,
      previousAverage,
      change,
      range: scores.length ? { low: Math.min(...scores), high: Math.max(...scores) } : null,
      contexts,
    };
  }, [logs]);

  const availableTags = useMemo(() => {
    const set = new Set([...COMMON_TAGS, ...customTagsList]);
    return Array.from(set);
  }, [customTagsList]);

  const getScoreDescriptor = (val: number) => {
    if (val <= 3) return "Low / Struggling";
    if (val <= 6) return "Neutral / Balanced";
    return "Positive / Uplifted";
  };

  const getScoreTone = (val: number) => {
    if (val <= 3) return "bg-rose-500";
    if (val <= 6) return "bg-amber-400";
    return "bg-emerald-500";
  };

  const changeDescription = () => {
    if (reflection.recentAverage === null) return "Log at least one check-in to begin.";
    if (reflection.total < 4 || reflection.change === null) {
      return `Your recent ${reflection.recent.length} check-in${reflection.recent.length > 1 ? "s" : ""} average ${reflection.recentAverage.toFixed(1)} / 10. Keep checking in to observe shifts over time.`;
    }
    if (reflection.change >= 0.75) return `Your most recent check-ins average ${reflection.change.toFixed(1)} points higher than your previous set.`;
    if (reflection.change <= -0.75) return `Your most recent check-ins average ${Math.abs(reflection.change).toFixed(1)} points lower than your previous set.`;
    return "Your check-ins are holding broadly steady compared to your previous set.";
  };

  const showMessage = (text: string, type: "success" | "error" = "success") => {
    setStatusMessage({ text, type });
    if (messageTimerRef.current) clearTimeout(messageTimerRef.current);
    messageTimerRef.current = setTimeout(() => setStatusMessage(null), 5000);
  };

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  };

  const handleAddCustomTag = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && customTag.trim()) {
      e.preventDefault();
      const clean = customTag.trim();
      if (!customTagsList.includes(clean)) {
        setCustomTagsList((prev) => [...prev, clean]);
      }
      if (!selectedTags.includes(clean)) {
        setSelectedTags((prev) => [...prev, clean]);
      }
      setCustomTag("");
    }
  };

  const removeCustomTag = (e: React.MouseEvent, tag: string) => {
    e.stopPropagation();
    setCustomTagsList((prev) => prev.filter((t) => t !== tag));
    setSelectedTags((prev) => prev.filter((t) => t !== tag));
  };

  const handleSliderKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowLeft" || e.key === "ArrowDown") {
      e.preventDefault();
      setScore((prev) => Math.max(1, prev - 1));
    } else if (e.key === "ArrowRight" || e.key === "ArrowUp") {
      e.preventDefault();
      setScore((prev) => Math.min(10, prev + 1));
    } else if (e.key === "Home") {
      e.preventDefault();
      setScore(1);
    } else if (e.key === "End") {
      e.preventDefault();
      setScore(10);
    }
  };

  const handleFocusLogForm = () => {
    if (typeof formRef.current?.scrollIntoView === "function") {
      formRef.current.scrollIntoView({ behavior: "smooth" });
    }
    sliderRef.current?.focus();
  };

  const addMood = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!token) return showMessage("Please sign in to save personal mood check-ins.", "error");

    const now = Date.now();
    if (now - lastSubmitRef.current < 1500) return;
    lastSubmitRef.current = now;

    setIsSubmitting(true);
    setStatusMessage(null);

    const allTags = [...selectedTags];
    if (customTag.trim() && !allTags.includes(customTag.trim())) {
      allTags.push(customTag.trim());
    }

    try {
      const response = await fetch("/api/moods", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          score,
          tags: allTags,
          notes
        })
      });
      let result: any = null;
      try {
        result = await response.json();
      } catch {
        if (!response.ok) {
          throw new Error(`Server error (${response.status}): Backend service is offline.`);
        }
        throw new Error("Invalid response received from server.");
      }
      if (!response.ok || result.success === false) {
        throw new Error(result?.error?.message || "Could not save mood entry.");
      }
      setLogs((current) => [...current, result.data.mood_log]);
      onMoodCreated?.(result.data.mood_log);
      setSelectedTags([]);
      setCustomTag("");
      setNotes("");
      showMessage("Mood entry saved successfully.", "success");
    } catch (err) {
      showMessage((err as Error).message, "error");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="min-h-0 flex-1 overflow-y-auto bg-slate-50 p-4 sm:p-8 font-sans" aria-label="Mood and analytics dashboard">
      <div className="mx-auto max-w-4xl space-y-6">
        {/* Section Header */}
        <div className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-200/90 pb-4">
          <div>
            <h1 className="text-xl font-bold text-slate-900 font-heading sm:text-2xl">
              Check-ins &amp; Reflections
            </h1>
            <p className="mt-0.5 text-xs text-slate-600 sm:text-sm font-normal">
              A private record to help you notice what is changing—not a scorecard or diagnosis.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <label htmlFor="analytics-period" className="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
              <Calendar className="size-3.5 text-indigo-600" />
              <span>Range:</span>
            </label>
            <select
              id="analytics-period"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              className="rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 shadow-2xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 cursor-pointer"
            >
              <option value="daily">Today</option>
              <option value="weekly">Last 7 days</option>
              <option value="monthly">Last 30 days</option>
              <option value="yearly">Last year</option>
            </select>
          </div>
        </div>

        {/* Non-Diagnostic Disclaimer Banner */}
        <div className="flex items-start gap-3 rounded-2xl border border-blue-200 bg-blue-50/80 p-3.5 text-xs leading-relaxed text-blue-950 shadow-2xs">
          <Info className="mt-0.5 size-4 shrink-0 text-blue-600" />
          <p className="font-normal">
            <strong>Use this as a reflection tool:</strong> it can describe your own check-ins and contexts, but it cannot explain why you feel a certain way, predict risk, or diagnose a condition.
          </p>
        </div>

        {/* Empty State Banner when no logs exist */}
        {logs.length === 0 && (
          <div className="rounded-2xl border border-indigo-100 bg-white p-6 text-center shadow-xs fade-in">
            <div className="mx-auto mb-3 grid size-12 place-items-center rounded-2xl bg-indigo-50 text-indigo-600">
              <Activity className="size-6" />
            </div>
            <h2 className="text-base font-bold text-slate-900 font-heading">Start with one honest check-in</h2>
            <p className="mx-auto mt-1 max-w-md text-xs text-slate-600 leading-relaxed font-normal">
              A score plus one context tag is enough. After three check-ins, this page can begin describing your recent pattern.
            </p>
            <button
              type="button"
              onClick={handleFocusLogForm}
              className="mt-4 inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-bold text-white shadow-xs transition-colors hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 cursor-pointer"
            >
              <Plus className="size-4" /> Log your first mood check-in
            </button>
          </div>
        )}

        {/* Reflection snapshot */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-2xs">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-600">
              <span>Check-ins</span>
              <Activity className="size-3.5 text-indigo-600" />
            </div>
            <p className="mt-2 text-2xl font-bold text-slate-900 font-heading">{reflection.total}</p>
          </div>

          <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-2xs">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-600">
              <span>Recent average</span>
              <TrendingUp className="size-3.5 text-emerald-600" />
            </div>
            <p className="mt-2 text-2xl font-bold text-slate-900 font-heading">{reflection.recentAverage?.toFixed(1) || "–"} <span className="text-xs font-medium text-slate-500">/ 10</span></p>
          </div>

          <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-2xs">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-600">
              <span>Recent range</span>
              <BarChart3 className="size-3.5 text-purple-600" />
            </div>
            <p className="mt-2 text-2xl font-bold text-slate-900 font-heading">{reflection.range ? `${reflection.range.low}–${reflection.range.high}` : "–"}</p>
          </div>
        </div>

        {/* Meaningful reflection: recent change, visible entries, and context only with enough data. */}
        {reflection.total > 0 && (
          <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
            <section className="rounded-2xl border border-indigo-200 bg-indigo-50/70 p-4 text-xs text-indigo-950 shadow-2xs" aria-label="Recent check-in reflection">
              <div className="flex items-center gap-2 font-bold font-heading text-indigo-900"><TrendingUp className="size-4 text-indigo-600" /><span>Your recent check-in story</span></div>
              <p className="mt-1 leading-relaxed font-normal">{changeDescription()}</p>
              <div className="mt-4 flex items-end justify-around sm:justify-start gap-2 h-24 pt-2 px-3 bg-indigo-100/40 rounded-xl" role="list" aria-label="Recent mood ratings">
                {reflection.recent.map((log, index) => {
                  const heightPercent = Math.max(20, (Number(log.score || 5) / 10) * 100);
                  return (
                    <div key={log.id || index} role="listitem" className="flex flex-col items-center justify-end h-full w-8 sm:w-10 text-center" title={`${log.score}/10${log.created_at ? ` on ${new Date(log.created_at).toLocaleDateString()}` : ""}`}>
                      <span className="text-[10px] font-bold text-slate-700 mb-1">{log.score}</span>
                      <div
                        className={`w-full rounded-t-md ${getScoreTone(log.score)} shadow-xs transition-all duration-300`}
                        style={{ height: `${heightPercent}%`, opacity: 0.55 + Number(log.score || 5) / 22 }}
                      />
                    </div>
                  );
                })}
              </div>
              <p className="mt-2 text-[11px] text-slate-600">Each bar is one self-reported check-in. A change is a prompt to reflect, not proof of a cause.</p>
            </section>

            <section className="rounded-2xl border border-slate-200/90 bg-white p-4 text-xs shadow-2xs" aria-label="Context observations">
              <div className="flex items-center gap-2 font-bold font-heading text-slate-900"><Compass className="size-4 text-indigo-600" /><span>Contexts you have logged</span></div>
              {reflection.contexts.length > 0 ? (
                <ul className="mt-3 space-y-2">
                  {reflection.contexts.map((context) => <li key={context.tag} className="rounded-xl bg-slate-50 px-3 py-2 text-slate-700"><strong className="capitalize text-slate-900">#{context.tag}</strong> appeared in {context.count} check-ins; those entries averaged {context.average.toFixed(1)} / 10.</li>)}
                </ul>
              ) : <p className="mt-2 leading-relaxed text-slate-600">Add the same context tag to at least two check-ins to see a careful comparison here.</p>}
            </section>
          </div>
        )}

        {reflection.total >= 3 && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-950 shadow-2xs">
            <div><p className="font-bold">Turn an observation into a small next step</p><p className="mt-0.5 text-emerald-900">If a pattern stands out, talk it through rather than treating a number as an answer.</p></div>
            {onStartChat && <button type="button" onClick={onStartChat} className="inline-flex items-center gap-2 rounded-xl bg-emerald-700 px-3.5 py-2 text-xs font-bold text-white hover:bg-emerald-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 cursor-pointer"><MessageCircle className="size-3.5" /> Talk it through</button>}
          </div>
        )}

        {/* Status Message / Save Feedback */}
        {statusMessage && (
          <div
            role="status"
            aria-live="polite"
            className={`flex items-center gap-2 rounded-xl border p-3 text-xs font-semibold shadow-2xs ${
              statusMessage.type === "success"
                ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                : "border-rose-200 bg-rose-50 text-rose-900"
            }`}
          >
            {statusMessage.type === "success" ? (
              <CheckCircle2 className="size-4 text-emerald-600 shrink-0" />
            ) : (
              <AlertCircle className="size-4 text-rose-600 shrink-0" />
            )}
            <span>{statusMessage.text}</span>
          </div>
        )}

        {/* Log Mood Check-in Form */}
        <form ref={formRef} onSubmit={addMood} className="space-y-4 rounded-2xl border border-slate-200/90 bg-white p-5 shadow-2xs">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <h2 className="flex items-center gap-2 text-base font-bold text-slate-900 font-heading">
              <Plus className="size-4 text-indigo-600" /> A quick check-in
            </h2>
            <span className="text-xs font-bold text-indigo-700 bg-indigo-50 border border-indigo-200/80 px-2.5 py-0.5 rounded-full">
              Score: {score} / 10 ({getScoreDescriptor(score)})
            </span>
          </div>

          <div>
            <label htmlFor="mood-score-range" className="block text-xs font-semibold text-slate-700 mb-1">
              How are you feeling right now? (1 = very low, 10 = very good)
            </label>
            <input
              id="mood-score-range"
              ref={sliderRef}
              type="range"
              min="1"
              max="10"
              step="1"
              value={score}
              aria-valuemin={1}
              aria-valuemax={10}
              aria-valuenow={score}
              aria-valuetext={`${score} out of 10, ${getScoreDescriptor(score)}`}
              onChange={(e) => setScore(Number(e.target.value))}
              onKeyDown={handleSliderKeyDown}
              className="w-full accent-indigo-600 cursor-pointer"
            />
            <div className="flex justify-between text-[11px] text-slate-600 font-medium px-0.5 mt-1">
              <span>1 - Low / Struggling</span>
              <span>5 - Neutral / Balanced</span>
              <span>10 - Positive / Uplifted</span>
            </div>

            {score <= 3 && (
              <div className="mt-2.5 rounded-xl border border-rose-200 bg-rose-50/80 p-2.5 text-[11px] text-rose-900 flex items-start gap-2">
                <Info className="size-3.5 text-rose-500 shrink-0 mt-0.5" />
                <div className="leading-relaxed">
                  <p>It takes honesty to notice when things feel heavy. You don’t have to fix everything right now.</p>
                  {onStartChat && (
                    <button
                      type="button"
                      onClick={onStartChat}
                      className="mt-1 font-semibold text-rose-700 underline hover:text-rose-900 cursor-pointer"
                    >
                      Would you like to talk it through in chat?
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Interactive Tag Chips */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1.5">
              What is around this feeling? (choose any that fit)
            </label>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {availableTags.map((tag) => {
                const isSelected = selectedTags.includes(tag);
                const isCustom = !COMMON_TAGS.includes(tag);
                return (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => toggleTag(tag)}
                    aria-pressed={isSelected}
                    className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium transition-colors cursor-pointer ${
                      isSelected
                        ? "border border-indigo-300 bg-indigo-50 text-indigo-900 font-semibold"
                        : "border border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100"
                    }`}
                  >
                    <span>#{tag}</span>
                    {isCustom && (
                      <span
                        role="button"
                        tabIndex={0}
                        onClick={(e) => removeCustomTag(e, tag)}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") removeCustomTag(e as any, tag); }}
                        aria-label={`Remove tag ${tag}`}
                        className="text-xs text-indigo-400 hover:text-indigo-800 font-bold ml-1 hover:bg-indigo-100 rounded-full px-1 cursor-pointer"
                      >
                        &times;
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
            <input
              type="text"
              placeholder="Type custom tag and press Enter..."
              value={customTag}
              onChange={(e) => setCustomTag(e.target.value)}
              onKeyDown={handleAddCustomTag}
              aria-label="Add custom tag"
              className="w-full rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            />
          </div>

          <div>
            <label htmlFor="mood-notes-input" className="block text-xs font-semibold text-slate-700 mb-1">
              What would you like to remember? (optional)
            </label>
            <textarea
              id="mood-notes-input"
              rows={2}
              placeholder="A short note for your future self—no need to explain everything."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 leading-relaxed"
            />
          </div>

          <div className="flex items-center gap-3 pt-1">
            <button
              type="submit"
              disabled={isSubmitting}
              className="rounded-xl bg-indigo-600 px-5 py-2 text-xs font-semibold text-white shadow-2xs transition-colors hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-50 cursor-pointer"
            >
              {isSubmitting ? "Saving Check-in..." : "Save check-in"}
            </button>
          </div>
        </form>

        {/* Recent Mood Entries Log */}
        <div className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-2xs">
          <div className="mb-4 flex items-center justify-between border-b border-slate-100 pb-3">
            <h2 className="flex items-center gap-2 text-base font-bold text-slate-900 font-heading">
              <Activity className="size-4 text-indigo-600" /> Your recent check-ins
            </h2>
            {onClearLogs && logs.length > 0 && (
              <button
                type="button"
                onClick={onClearLogs}
                className="flex items-center gap-1 text-xs font-semibold text-rose-700 hover:text-rose-900 transition-colors cursor-pointer"
              >
                <Trash2 className="size-3.5" /> Wipe History
              </button>
            )}
          </div>

          {logs.length > 0 ? (
            <div className="space-y-2.5">
              {logs.slice().reverse().slice(0, 10).map((log, index) => (
                <article key={log.id || index} className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3.5 transition-colors hover:bg-slate-50">
                  <div className="flex items-center justify-between gap-3">
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-0.5 text-xs font-bold text-indigo-900">
                      Mood {log.score} / 10 • {getScoreDescriptor(log.score)}
                    </span>
                    <time className="text-xs text-slate-600">
                      {log.created_at ? new Date(log.created_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" }) : "Just now"}
                    </time>
                  </div>
                  {log.tags && log.tags.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {log.tags.map((t, idx) => (
                        <span key={idx} className="rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-700">
                          #{t}
                        </span>
                      ))}
                    </div>
                  )}
                  {log.notes && <p className="mt-2 text-xs leading-relaxed text-slate-800 font-normal">{log.notes}</p>}
                </article>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-500 py-4 text-center">No mood check-ins recorded yet for this time range.</p>
          )}
        </div>
      </div>
    </section>
  );
}
