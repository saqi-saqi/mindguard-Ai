import React, { useEffect, useMemo, useRef, useState } from "react";
import { Activity, Plus, Trash2, Calendar, Info, BarChart3, TrendingUp, Sparkles, CheckCircle2, AlertCircle } from "lucide-react";
import type { MoodLog } from "./types";

interface Props {
  moodLogs?: MoodLog[];
  onClearLogs?: () => void;
  token?: string;
  onMoodCreated?: (log: MoodLog) => void;
}

const COMMON_TAGS = ["Exam", "Sleep", "Exercise", "Work", "Family", "Social", "Study", "Relaxation"];

export default function AnalyticsDashboard({ moodLogs = [], onClearLogs, token, onMoodCreated }: Props) {
  const [period, setPeriod] = useState("monthly");
  const [logs, setLogs] = useState<MoodLog[]>(moodLogs);
  const [usage, setUsage] = useState({ message_count: 0, session_count: 0 });
  const [score, setScore] = useState(5);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
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
          setUsage(data.data);
        }
      })
      .catch(() => showMessage("Could not load analytics summary.", "error"));
  }, [period, token]);

  const summary = useMemo(() => {
    const total = logs.length;
    const average = total
      ? (logs.reduce((sum, log) => sum + Number(log.score || 0), 0) / total).toFixed(1)
      : "-";
    const positive = logs.filter((log) => log.score >= 7).length;
    const low = logs.filter((log) => log.score <= 3).length;
    return { total, average, positive, low };
  }, [logs]);

  // Cautious, non-causal co-occurrence trend insights requiring at least 5 records
  const trendInsight = useMemo(() => {
    if (logs.length < 5) return null;
    const tagFrequencies: Record<string, { count: number; lowScoreCount: number }> = {};
    logs.forEach((log) => {
      if (log.tags && Array.isArray(log.tags)) {
        log.tags.forEach((tag) => {
          const t = tag.trim().toLowerCase();
          if (!tagFrequencies[t]) tagFrequencies[t] = { count: 0, lowScoreCount: 0 };
          tagFrequencies[t].count += 1;
          if (log.score <= 4) tagFrequencies[t].lowScoreCount += 1;
        });
      }
    });

    let topLowTag: string | null = null;
    let maxLow = 0;
    Object.entries(tagFrequencies).forEach(([tag, stats]) => {
      if (stats.count >= 2 && stats.lowScoreCount >= 2 && stats.lowScoreCount > maxLow) {
        maxLow = stats.lowScoreCount;
        topLowTag = tag;
      }
    });

    if (topLowTag) {
      return `Topic "${topLowTag}" appeared frequently alongside lower mood scores. (Observed in ${maxLow} entries)`;
    }
    return null;
  }, [logs]);

  const getScoreDescriptor = (val: number) => {
    if (val <= 3) return "Low / Struggling";
    if (val <= 6) return "Neutral / Balanced";
    return "Positive / Uplifted";
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
      if (!selectedTags.includes(clean)) {
        setSelectedTags((prev) => [...prev, clean]);
      }
      setCustomTag("");
    }
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
              Mood &amp; Activity Analytics
            </h1>
            <p className="mt-0.5 text-xs text-slate-600 sm:text-sm font-normal">
              Track personal self-reported emotional trends and interactions over time.
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
              <option value="daily">Daily View</option>
              <option value="weekly">Weekly View</option>
              <option value="monthly">Monthly View</option>
              <option value="yearly">Yearly View</option>
            </select>
          </div>
        </div>

        {/* Non-Diagnostic Disclaimer Banner */}
        <div className="flex items-start gap-3 rounded-2xl border border-blue-200 bg-blue-50/80 p-3.5 text-xs leading-relaxed text-blue-950 shadow-2xs">
          <Info className="mt-0.5 size-4 shrink-0 text-blue-600" />
          <p className="font-normal">
            <strong>Self-Reflection Disclaimer:</strong> Mood trends and analytics reported here are for personal track-keeping and self-reflection only. They do not constitute a clinical medical diagnosis, psychological test, or formal clinical assessment.
          </p>
        </div>

        {/* Empty State Banner when no logs exist */}
        {logs.length === 0 && (
          <div className="rounded-2xl border border-indigo-100 bg-white p-6 text-center shadow-xs fade-in">
            <div className="mx-auto mb-3 grid size-12 place-items-center rounded-2xl bg-indigo-50 text-indigo-600">
              <Activity className="size-6" />
            </div>
            <h2 className="text-base font-bold text-slate-900 font-heading">Start Tracking Your Emotional Well-being</h2>
            <p className="mx-auto mt-1 max-w-md text-xs text-slate-600 leading-relaxed font-normal">
              Your mood history and reflection trends will appear here after your first check-in.
              Regular check-ins help identify personal coping patterns.
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

        {/* Stat Cards */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-2xs">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-600">
              <span>Total Entries</span>
              <Activity className="size-3.5 text-indigo-600" />
            </div>
            <p className="mt-2 text-2xl font-bold text-slate-900 font-heading">{summary.total}</p>
          </div>

          <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-2xs">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-600">
              <span>Average Score</span>
              <TrendingUp className="size-3.5 text-emerald-600" />
            </div>
            <p className="mt-2 text-2xl font-bold text-slate-900 font-heading">{summary.average} <span className="text-xs font-medium text-slate-500">/ 10</span></p>
          </div>

          <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-2xs">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-600">
              <span>Positive Days (7-10)</span>
              <Sparkles className="size-3.5 text-purple-600" />
            </div>
            <p className="mt-2 text-2xl font-bold text-slate-900 font-heading">{summary.positive}</p>
          </div>

          <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-2xs">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-600">
              <span>Messages / Sessions</span>
              <BarChart3 className="size-3.5 text-cyan-600" />
            </div>
            <p className="mt-2 text-2xl font-bold text-slate-900 font-heading">
              {usage.message_count} <span className="text-xs font-medium text-slate-500">/ {usage.session_count}</span>
            </p>
          </div>
        </div>

        {/* Cautious Trend Insight (Displayed only when sufficient data exists) */}
        {trendInsight && (
          <div className="rounded-2xl border border-indigo-200 bg-indigo-50/70 p-4 text-xs text-indigo-950 shadow-2xs">
            <div className="flex items-center gap-2 font-bold font-heading text-indigo-900 mb-1">
              <TrendingUp className="size-4 text-indigo-600" />
              <span>Self-Reflection Pattern</span>
            </div>
            <p className="leading-relaxed font-normal">{trendInsight}</p>
            <p className="text-[11px] text-slate-500 mt-1">
              Note: Patterns describe correlation in your entries, not medical causation or diagnosis.
            </p>
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
              <Plus className="size-4 text-indigo-600" /> Log Mood Check-in
            </h2>
            <span className="text-xs font-bold text-indigo-700 bg-indigo-50 border border-indigo-200/80 px-2.5 py-0.5 rounded-full">
              Score: {score} / 10 ({getScoreDescriptor(score)})
            </span>
          </div>

          <div>
            <label htmlFor="mood-score-range" className="block text-xs font-semibold text-slate-700 mb-1">
              Select Mood Rating (1 = Lowest, 10 = Best)
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
          </div>

          {/* Interactive Tag Chips */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1.5">
              Select Activity &amp; Context Tags
            </label>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {COMMON_TAGS.map((tag) => {
                const isSelected = selectedTags.includes(tag);
                return (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => toggleTag(tag)}
                    aria-pressed={isSelected}
                    className={`rounded-full px-3 py-1 text-xs font-medium transition-colors cursor-pointer ${
                      isSelected
                        ? "border border-indigo-300 bg-indigo-50 text-indigo-900 font-semibold"
                        : "border border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100"
                    }`}
                  >
                    #{tag}
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
              Optional Reflection Notes
            </label>
            <textarea
              id="mood-notes-input"
              rows={2}
              placeholder="Short personal reflection on what contributed to this rating..."
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
              {isSubmitting ? "Saving Check-in..." : "Save Mood Entry"}
            </button>
          </div>
        </form>

        {/* Recent Mood Entries Log */}
        <div className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-2xs">
          <div className="mb-4 flex items-center justify-between border-b border-slate-100 pb-3">
            <h2 className="flex items-center gap-2 text-base font-bold text-slate-900 font-heading">
              <Activity className="size-4 text-indigo-600" /> Recent Mood History
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
