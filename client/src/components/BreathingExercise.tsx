import React, { useState, useEffect, useCallback, useRef } from "react";
import { X, Wind, Play, Square, RotateCcw } from "lucide-react";

// ─── Types & Config ──────────────────────────────────────────────────────────

interface BreathPhase {
  label: string;
  seconds: number;
  instruction: string;
  color: string;      // Tailwind bg for the circle
  ringColor: string;  // stroke color for SVG ring
  scale: number;      // how large the circle animates to
}

interface BreathingPattern {
  id: string;
  name: string;
  shortName: string;
  description: string;
  phases: BreathPhase[];
  totalCycles: number;     // recommended full cycles
}

const PATTERNS: BreathingPattern[] = [
  {
    id: "478",
    name: "4-7-8 Relaxation",
    shortName: "4-7-8",
    description: "Calms the nervous system. Inhale 4s, hold 7s, exhale 8s.",
    totalCycles: 4,
    phases: [
      { label: "Inhale",  seconds: 4, instruction: "Breathe in slowly through your nose",       color: "bg-indigo-500",  ringColor: "#6366f1", scale: 1.15 },
      { label: "Hold",    seconds: 7, instruction: "Hold your breath gently — don't strain",    color: "bg-purple-500",  ringColor: "#a855f7", scale: 1.15 },
      { label: "Exhale",  seconds: 8, instruction: "Breathe out fully through your mouth",      color: "bg-sky-500",     ringColor: "#0ea5e9", scale: 0.85 },
    ],
  },
  {
    id: "box",
    name: "Box Breathing",
    shortName: "Box 4-4-4-4",
    description: "Used by first responders to regain calm. Four equal sides.",
    totalCycles: 4,
    phases: [
      { label: "Inhale",      seconds: 4, instruction: "Inhale slowly through your nose",          color: "bg-indigo-500",   ringColor: "#6366f1", scale: 1.15 },
      { label: "Hold In",     seconds: 4, instruction: "Hold at the top",                           color: "bg-violet-500",   ringColor: "#8b5cf6", scale: 1.15 },
      { label: "Exhale",      seconds: 4, instruction: "Exhale slowly through your mouth",          color: "bg-sky-500",      ringColor: "#0ea5e9", scale: 0.85 },
      { label: "Hold Out",    seconds: 4, instruction: "Hold at the bottom, ready for next inhale", color: "bg-slate-400",    ringColor: "#94a3b8", scale: 0.85 },
    ],
  },
  {
    id: "simple",
    name: "Simple Calm",
    shortName: "5-5 Simple",
    description: "Easiest pattern. Breathe in for 5, breathe out for 5.",
    totalCycles: 6,
    phases: [
      { label: "Inhale", seconds: 5, instruction: "Breathe in gently through your nose",  color: "bg-teal-500",  ringColor: "#14b8a6", scale: 1.15 },
      { label: "Exhale", seconds: 5, instruction: "Breathe out slowly through your mouth", color: "bg-cyan-500",  ringColor: "#06b6d4", scale: 0.85 },
    ],
  },
];

// ─── SVG Progress Ring ────────────────────────────────────────────────────────

function ProgressRing({
  radius,
  strokeWidth,
  progress,    // 0 → 1
  color,
}: {
  radius: number;
  strokeWidth: number;
  progress: number;
  color: string;
}) {
  const normalizedRadius = radius - strokeWidth / 2;
  const circumference = 2 * Math.PI * normalizedRadius;
  const strokeDashoffset = circumference * (1 - progress);

  return (
    <svg
      height={radius * 2}
      width={radius * 2}
      className="absolute inset-0 -rotate-90"
      aria-hidden="true"
    >
      {/* Track */}
      <circle
        stroke="#e2e8f0"
        fill="transparent"
        strokeWidth={strokeWidth}
        r={normalizedRadius}
        cx={radius}
        cy={radius}
      />
      {/* Progress */}
      <circle
        stroke={color}
        fill="transparent"
        strokeWidth={strokeWidth}
        strokeDasharray={`${circumference} ${circumference}`}
        strokeDashoffset={strokeDashoffset}
        strokeLinecap="round"
        r={normalizedRadius}
        cx={radius}
        cy={radius}
        style={{ transition: "stroke-dashoffset 1s linear" }}
      />
    </svg>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

interface BreathingExerciseProps {
  onClose: () => void;
  /** Which pattern to start on (defaults to '478') */
  initialPatternId?: string;
  /** Auto-start when mounted */
  autoStart?: boolean;
}

export default function BreathingExercise({
  onClose,
  initialPatternId = "478",
  autoStart = false,
}: BreathingExerciseProps) {
  const [selectedPatternId, setSelectedPatternId] = useState(initialPatternId);
  const [isRunning, setIsRunning] = useState(autoStart);
  const [phaseIndex, setPhaseIndex] = useState(0);
  const pattern = PATTERNS.find((p) => p.id === selectedPatternId) ?? PATTERNS[0];
  const phase = pattern.phases[phaseIndex];
  const [secondsLeft, setSecondsLeft] = useState<number>(phase.seconds);
  const [cyclesCompleted, setCyclesCompleted] = useState(0);
  const [finished, setFinished] = useState(false);

  // Initialise or reset seconds when phase changes or pattern changes
  const didMountRef = useRef(false);
  useEffect(() => {
    setSecondsLeft(phase.seconds);
  }, [phaseIndex, selectedPatternId, phase.seconds]);

  // Reset fully when pattern selection changes
  useEffect(() => {
    if (!didMountRef.current) { didMountRef.current = true; return; }
    setPhaseIndex(0);
    setCyclesCompleted(0);
    setFinished(false);
    setIsRunning(false);
    setSecondsLeft(pattern.phases[0].seconds);
  }, [selectedPatternId, pattern.phases]);

  // Tick
  useEffect(() => {
    if (!isRunning || finished) return;
    const id = setInterval(() => {
      setSecondsLeft((prev) => {
        if (prev <= 1) {
          // Advance to next phase
          setPhaseIndex((prevPhase) => {
            const next = (prevPhase + 1) % pattern.phases.length;
            // Completed a full cycle when we wrap to phase 0
            if (next === 0) {
              setCyclesCompleted((c) => {
                const newCount = c + 1;
                if (newCount >= pattern.totalCycles) {
                  setFinished(true);
                  setIsRunning(false);
                }
                return newCount;
              });
            }
            return next;
          });
          return phase.seconds; // temp, will be overwritten by the phaseIndex effect
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [isRunning, finished, phase.seconds, pattern.phases.length, pattern.totalCycles]);

  const handleReset = useCallback(() => {
    setPhaseIndex(0);
    setCyclesCompleted(0);
    setFinished(false);
    setIsRunning(false);
    setSecondsLeft(pattern.phases[0].seconds);
  }, [pattern]);

  const progress = secondsLeft / phase.seconds; // 1 → 0 as time elapses
  const ringProgress = 1 - progress;            // 0 → 1 for the progress ring fill

  // Circle scale: animate between base size and phase.scale
  const circleScale = isRunning
    ? phase.scale
    : 1.0;

  return (
    <div
      role="region"
      aria-label="Breathing exercise"
      className="mt-2 rounded-2xl border border-indigo-200 bg-gradient-to-b from-indigo-50 to-white p-4 shadow-sm fade-in"
    >
      {/* Header Row */}
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Wind className="size-4 text-indigo-600" />
          <span className="text-sm font-bold text-indigo-900">Guided Breathing Exercise</span>
          {isRunning ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-800">
              <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Exercise Active
            </span>
          ) : !finished && (
            <span className="inline-flex items-center rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-medium text-slate-600">
              {cyclesCompleted > 0 || phaseIndex > 0 ? "Paused" : "Ready"}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close breathing exercise"
          className="rounded-lg p-1 text-slate-400 hover:bg-indigo-100 hover:text-slate-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 cursor-pointer"
        >
          <X className="size-4" />
        </button>
      </div>

      {/* Pattern Selector */}
      <div className="mb-4 flex flex-wrap gap-1.5">
        {PATTERNS.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => setSelectedPatternId(p.id)}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 cursor-pointer ${
              selectedPatternId === p.id
                ? "bg-indigo-600 text-white shadow-xs"
                : "border border-slate-200 bg-white text-slate-600 hover:border-indigo-300 hover:text-indigo-800"
            }`}
          >
            {p.shortName}
          </button>
        ))}
      </div>

      {/* Pattern Description */}
      <p className="mb-4 text-xs text-slate-500 leading-relaxed">{pattern.description}</p>

      {/* Main Visual */}
      {finished ? (
        /* Completion State */
        <div className="flex flex-col items-center gap-3 py-4">
          <div className="text-4xl">✅</div>
          <p className="text-center text-sm font-bold text-indigo-900">
            Well done! You completed {cyclesCompleted} cycle{cyclesCompleted !== 1 ? "s" : ""}.
          </p>
          <p className="text-center text-xs text-slate-500">
            Take a moment to notice how your body feels. You can restart anytime.
          </p>
          <button
            type="button"
            onClick={handleReset}
            className="mt-1 inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-indigo-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 cursor-pointer"
          >
            <RotateCcw className="size-3.5" /> Restart
          </button>
        </div>
      ) : (
        /* Active / Idle State */
        <div className="flex flex-col items-center gap-4">
          {/* Animated Circle with Progress Ring */}
          <div className="relative flex items-center justify-center" style={{ width: 136, height: 136 }}>
            {/* SVG Ring */}
            <ProgressRing
              radius={68}
              strokeWidth={6}
              progress={ringProgress}
              color={phase.ringColor}
            />

            {/* Central pulsing circle */}
            <div
              className={`relative z-10 flex flex-col items-center justify-center rounded-full text-white shadow-lg transition-all ${phase.color}`}
              style={{
                width: 96,
                height: 96,
                transform: `scale(${circleScale})`,
                transition: isRunning
                  ? `transform ${phase.seconds}s ease-in-out`
                  : "transform 0.3s ease",
              }}
            >
              <span className="text-2xl font-bold leading-none tabular-nums">{secondsLeft}</span>
              <span className="text-[10px] font-semibold uppercase tracking-wide opacity-90 mt-0.5">
                sec
              </span>
            </div>
          </div>

          {/* Phase Label & Instruction */}
          <div className="text-center">
            <p className="text-lg font-bold text-slate-900">{phase.label}</p>
            <p className="mt-0.5 text-xs text-slate-500">{phase.instruction}</p>
          </div>

          {/* Cycle Progress Dots */}
          <div className="flex items-center gap-1.5" aria-label={`${cyclesCompleted} of ${pattern.totalCycles} cycles completed`}>
            {Array.from({ length: pattern.totalCycles }).map((_, i) => (
              <span
                key={i}
                className={`size-2 rounded-full transition-colors ${
                  i < cyclesCompleted ? "bg-indigo-500" : "bg-slate-200"
                }`}
              />
            ))}
            <span className="ml-1 text-[11px] text-slate-400">
              {cyclesCompleted}/{pattern.totalCycles} cycles
            </span>
          </div>

          {/* Controls */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsRunning((r) => !r)}
              className={`inline-flex items-center gap-1.5 rounded-xl px-5 py-2 text-xs font-bold text-white shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 cursor-pointer ${
                isRunning
                  ? "bg-slate-500 hover:bg-slate-600"
                  : "bg-indigo-600 hover:bg-indigo-700"
              }`}
            >
              {isRunning ? (
                <><Square className="size-3.5" /> Pause</>
              ) : (
                <><Play className="size-3.5" /> {cyclesCompleted === 0 ? "Start" : "Resume"}</>
              )}
            </button>
            {(cyclesCompleted > 0 || phaseIndex > 0) && (
              <button
                type="button"
                onClick={handleReset}
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 shadow-xs hover:bg-slate-50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 cursor-pointer"
              >
                <RotateCcw className="size-3.5" /> Reset
              </button>
            )}
          </div>
        </div>
      )}

      {/* Phase sequence hint */}
      {!finished && (
        <div className="mt-4 flex flex-wrap items-center justify-center gap-1.5 border-t border-slate-100 pt-3">
          {pattern.phases.map((p, i) => (
            <React.Fragment key={i}>
              <span
                className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold transition-colors ${
                  i === phaseIndex && isRunning
                    ? `${p.color} text-white`
                    : "bg-slate-100 text-slate-500"
                }`}
              >
                {p.label} {p.seconds}s
              </span>
              {i < pattern.phases.length - 1 && (
                <span className="text-slate-300 text-xs">→</span>
              )}
            </React.Fragment>
          ))}
        </div>
      )}

      {/* Non-clinical note */}
      <p className="mt-3 text-center text-[10px] text-slate-400 italic">
        Breathing exercises are self-help wellness tools, not medical treatment.
      </p>
    </div>
  );
}
