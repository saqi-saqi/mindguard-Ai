import { useState, useEffect, useCallback } from "react";
import {
  ShieldAlert,
  Filter,
  CheckCircle2,
  Clock,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  FileText,
  Lock,
  ArrowLeft,
  X,
  Search,
} from "lucide-react";
import type { MindUser, SafetyLogEntry, SafetyLogStats } from "./types";

interface Props {
  user: MindUser | null;
  token?: string;
  onNavigateToAuth?: (mode: "login" | "register") => void;
  onBackToChat?: () => void;
}

export default function AdminSafetyLogs({
  user,
  token,
  onNavigateToAuth,
  onBackToChat,
}: Props) {
  const [logs, setLogs] = useState<SafetyLogEntry[]>([]);
  const [stats, setStats] = useState<SafetyLogStats | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit] = useState(15);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [selectedTier, setSelectedTier] = useState<string>("all");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [selectedResolved, setSelectedResolved] = useState<string>("all");
  const [selectedDateRange, setSelectedDateRange] = useState<string>("all");

  // Selected Log for Modal
  const [activeLog, setActiveLog] = useState<SafetyLogEntry | null>(null);
  const [modalResolved, setModalResolved] = useState(false);
  const [modalAdminNote, setModalAdminNote] = useState("");
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateSuccess, setUpdateSuccess] = useState<string | null>(null);

  const isAdmin = Boolean(user && user.role === "admin" && token);

  const fetchLogs = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);

    const params = new URLSearchParams();
    params.set("page", String(page));
    params.set("limit", String(limit));

    if (selectedTier !== "all") params.set("tier", selectedTier);
    if (selectedCategory !== "all") params.set("category", selectedCategory);
    if (selectedResolved !== "all") params.set("resolved", selectedResolved);

    // Date range calculations
    if (selectedDateRange !== "all") {
      const now = new Date();
      let startDt: Date;
      if (selectedDateRange === "24h") {
        startDt = new Date(now.getTime() - 24 * 60 * 60 * 1000);
      } else if (selectedDateRange === "7d") {
        startDt = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      } else if (selectedDateRange === "30d") {
        startDt = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      } else {
        startDt = new Date(0);
      }
      params.set("start_date", startDt.toISOString());
    }

    try {
      const res = await fetch(`/api/admin/safety-logs?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      const resData = await res.json().catch(() => null);

      if (!res.ok || resData?.success === false) {
        throw new Error(
          resData?.error?.message || `Failed to fetch safety logs (${res.status})`
        );
      }

      const data = resData.data;
      setLogs(data.logs || []);
      setTotal(data.total || 0);
      setTotalPages(data.total_pages || 1);
      if (data.stats) {
        setStats(data.stats);
      }
    } catch (err: any) {
      console.error("Error fetching safety logs:", err);
      setError(err.message || "Failed to load safety logs.");
    } finally {
      setLoading(false);
    }
  }, [token, page, limit, selectedTier, selectedCategory, selectedResolved, selectedDateRange]);

  useEffect(() => {
    if (isAdmin) {
      fetchLogs();
    }
  }, [isAdmin, fetchLogs]);

  // Open review modal
  const openReviewModal = (log: SafetyLogEntry) => {
    setActiveLog(log);
    setModalResolved(Boolean(log.resolved));
    setModalAdminNote(log.admin_note || "");
    setUpdateSuccess(null);
  };

  // Submit review update
  const handleSaveReview = async () => {
    if (!activeLog || !token) return;
    setIsUpdating(true);
    setUpdateSuccess(null);

    try {
      const res = await fetch(`/api/admin/safety-logs/${activeLog.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          resolved: modalResolved,
          admin_note: modalAdminNote,
        }),
      });

      const resData = await res.json().catch(() => null);

      if (!res.ok || resData?.success === false) {
        throw new Error(
          resData?.error?.message || "Failed to update safety log record."
        );
      }

      setUpdateSuccess("Safety review updated successfully.");
      // Refresh local item in list
      setLogs((prev) =>
        prev.map((item) => (item.id === activeLog.id ? resData.data : item))
      );
      // Refresh stats in background
      fetchLogs();

      setTimeout(() => {
        setActiveLog(null);
        setUpdateSuccess(null);
      }, 1200);
    } catch (err: any) {
      alert(`Update error: ${err.message || err}`);
    } finally {
      setIsUpdating(false);
    }
  };

  // Format date helper
  const formatDate = (isoString?: string) => {
    if (!isoString) return "—";
    try {
      const dt = new Date(isoString);
      return dt.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return isoString;
    }
  };

  // Non-Admin Gate Screen
  if (!isAdmin) {
    return (
      <div className="flex-1 flex items-center justify-center p-6 bg-slate-900 text-slate-100">
        <div className="max-w-md w-full rounded-2xl border border-rose-500/30 bg-slate-800/90 p-8 text-center shadow-xl space-y-4">
          <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-rose-500/10 text-rose-400">
            <Lock className="size-6" />
          </div>
          <h2 className="text-lg font-bold text-white font-heading">
            Administrator Access Required
          </h2>
          <p className="text-xs text-slate-300 leading-relaxed">
            The safety logs and clinical audit dashboard is restricted to authorized
            clinical administrators. Please sign in with an administrator account to
            access crisis audit records.
          </p>
          {user ? (
            <div className="rounded-xl border border-slate-700 bg-slate-900/80 p-3 text-left space-y-1.5 text-xs">
              <div className="flex items-center justify-between text-slate-400 text-[11px]">
                <span>Signed in as:</span>
                <span className="font-semibold text-slate-200">{user.email}</span>
              </div>
              <div className="flex items-center justify-between text-slate-400 text-[11px]">
                <span>Assigned Role:</span>
                <span className="font-mono font-bold text-amber-400">{user.role || "user"}</span>
              </div>
             </div>
          ) : (
            <div className="rounded-xl border border-slate-700 bg-slate-900/80 p-3 text-xs text-slate-400">
              You are currently browsing as a guest. Please sign in with an administrator account.
            </div>
          )}
          <div className="flex flex-col gap-2 pt-2">
            <button
              type="button"
              onClick={() => onNavigateToAuth?.("login")}
              className="rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-bold text-white transition hover:bg-indigo-500 cursor-pointer shadow-xs"
            >
              Sign In as Administrator
            </button>
            {onBackToChat && (
              <button
                type="button"
                onClick={onBackToChat}
                className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700 cursor-pointer"
              >
                Back to Chat
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-slate-900 text-slate-100 overflow-y-auto font-sans">
      <div className="max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
        {/* Top Header */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-5">
          <div className="flex items-center gap-3">
            {onBackToChat && (
              <button
                type="button"
                onClick={onBackToChat}
                className="p-2 rounded-xl border border-slate-800 bg-slate-800/60 text-slate-400 hover:text-white hover:bg-slate-700 transition cursor-pointer"
                title="Back to chat"
                aria-label="Back to chat"
              >
                <ArrowLeft className="size-4" />
              </button>
            )}
            <div className="grid size-10 place-items-center rounded-xl bg-rose-500/10 text-rose-400 border border-rose-500/20">
              <ShieldAlert className="size-5" />
            </div>
            <div>
              <h1 className="text-lg sm:text-xl font-bold text-white font-heading flex items-center gap-2">
                Crisis Safety Event Logs
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/30">
                  Admin Audit
                </span>
              </h1>
              <p className="text-xs text-slate-400">
                Audited records for Tier 1 regex rules, Tier 2 ML models, and Tier 3 LLM verification flags.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => fetchLogs()}
            disabled={loading}
            className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700 transition cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>

        {/* Dashboard Header Summary Stats */}
        {stats && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
            {/* Total Flags */}
            <div className="rounded-2xl border border-slate-800 bg-slate-800/60 p-4 shadow-xs">
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Total Crisis Flags
              </p>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-black text-white font-heading">
                  {stats.total_flags}
                </span>
                <span className="text-[11px] font-medium text-slate-400">
                  all-time
                </span>
              </div>
            </div>

            {/* Unresolved Incidents */}
            <div className="rounded-2xl border border-rose-500/20 bg-rose-500/5 p-4 shadow-xs">
              <p className="text-[11px] font-bold uppercase tracking-wider text-rose-300 flex items-center gap-1.5">
                <AlertTriangle className="size-3.5" /> Pending Review
              </p>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-black text-rose-400 font-heading">
                  {stats.unresolved_count}
                </span>
                <span className="text-[11px] font-medium text-slate-400">
                  unresolved
                </span>
              </div>
            </div>

            {/* Last 7 Days Flags */}
            <div className="rounded-2xl border border-slate-800 bg-slate-800/60 p-4 shadow-xs">
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Last 7 Days
              </p>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-black text-indigo-400 font-heading">
                  {stats.last_7_days.total}
                </span>
                <span className="text-[11px] font-medium text-slate-400">
                  T1: {stats.last_7_days.tier_1} | T2: {stats.last_7_days.tier_2} | T3: {stats.last_7_days.tier_3}
                </span>
              </div>
            </div>

            {/* Last 30 Days Flags */}
            <div className="rounded-2xl border border-slate-800 bg-slate-800/60 p-4 shadow-xs">
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Last 30 Days
              </p>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-black text-emerald-400 font-heading">
                  {stats.last_30_days.total}
                </span>
                <span className="text-[11px] font-medium text-slate-400">
                  T1: {stats.last_30_days.tier_1} | T2: {stats.last_30_days.tier_2} | T3: {stats.last_30_days.tier_3}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Filter Controls Bar */}
        <div className="rounded-2xl border border-slate-800 bg-slate-800/60 p-4 space-y-3">
          <div className="flex items-center gap-2 text-xs font-bold text-slate-300">
            <Filter className="size-4 text-indigo-400" />
            <span>Filter Safety Records</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {/* Tier Filter */}
            <div>
              <label htmlFor="filter-tier" className="block text-[11px] font-semibold text-slate-400 mb-1">
                Detection Tier
              </label>
              <select
                id="filter-tier"
                value={selectedTier}
                onChange={(e) => {
                  setSelectedTier(e.target.value);
                  setPage(1);
                }}
                className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer"
              >
                <option value="all">All Tiers (1, 2, 3)</option>
                <option value="1">Tier 1 (Deterministic Regex Rules)</option>
                <option value="2">Tier 2 (Machine Learning ML)</option>
                <option value="3">Tier 3 (LLM Safety Guardrail)</option>
              </select>
            </div>

            {/* Category Filter */}
            <div>
              <label htmlFor="filter-category" className="block text-[11px] font-semibold text-slate-400 mb-1">
                Crisis Category
              </label>
              <select
                id="filter-category"
                value={selectedCategory}
                onChange={(e) => {
                  setSelectedCategory(e.target.value);
                  setPage(1);
                }}
                className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer"
              >
                <option value="all">All Categories</option>
                <option value="self-harm">Self-Harm &amp; Suicide</option>
                <option value="homicide/threat-to-others">Homicide / Threat to Others</option>
                <option value="reported-threat-to-user">Reported Threat to User</option>
                <option value="reported-threat-to-others">Reported Threat to Others</option>
                <option value="combined_high_crisis">Combined Multi-Signal Crisis</option>
                <option value="third-party-report">Third-Party Report</option>
              </select>
            </div>

            {/* Status Filter */}
            <div>
              <label htmlFor="filter-status" className="block text-[11px] font-semibold text-slate-400 mb-1">
                Review Status
              </label>
              <select
                id="filter-status"
                value={selectedResolved}
                onChange={(e) => {
                  setSelectedResolved(e.target.value);
                  setPage(1);
                }}
                className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer"
              >
                <option value="all">All Records</option>
                <option value="false">Unresolved / Pending Review</option>
                <option value="true">Resolved &amp; Reviewed</option>
              </select>
            </div>

            {/* Date Range Filter */}
            <div>
              <label htmlFor="filter-date" className="block text-[11px] font-semibold text-slate-400 mb-1">
                Time Window
              </label>
              <select
                id="filter-date"
                value={selectedDateRange}
                onChange={(e) => {
                  setSelectedDateRange(e.target.value);
                  setPage(1);
                }}
                className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer"
              >
                <option value="all">All Time</option>
                <option value="24h">Past 24 Hours</option>
                <option value="7d">Past 7 Days</option>
                <option value="30d">Past 30 Days</option>
              </select>
            </div>
          </div>
        </div>

        {/* Error Notification */}
        {error && (
          <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 text-xs text-rose-300">
            {error}
          </div>
        )}

        {/* Main Table */}
        <div className="rounded-2xl border border-slate-800 bg-slate-800/40 overflow-hidden shadow-xs">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-800/80 text-[11px] font-bold uppercase tracking-wider text-slate-400 border-b border-slate-800">
                <tr>
                  <th scope="col" className="px-4 py-3">Timestamp</th>
                  <th scope="col" className="px-4 py-3">Tier</th>
                  <th scope="col" className="px-4 py-3">Category</th>
                  <th scope="col" className="px-4 py-3">Rule / Model</th>
                  <th scope="col" className="px-4 py-3">Action Taken</th>
                  <th scope="col" className="px-4 py-3">Redacted Excerpt</th>
                  <th scope="col" className="px-4 py-3">Status</th>
                  <th scope="col" className="px-4 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {loading && logs.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-12 text-center text-slate-400">
                      <RefreshCw className="size-5 animate-spin mx-auto mb-2 text-indigo-400" />
                      Loading safety logs...
                    </td>
                  </tr>
                ) : logs.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-12 text-center text-slate-400">
                      No crisis safety records match the selected filters.
                    </td>
                  </tr>
                ) : (
                  logs.map((log) => {
                    const isTier1 = log.tier === 1;
                    const isTier2 = log.tier === 2;
                    const isTier3 = log.tier === 3;

                    return (
                      <tr key={log.id} className="hover:bg-slate-800/40 transition-colors">
                        {/* Timestamp */}
                        <td className="px-4 py-3 whitespace-nowrap text-slate-300 font-mono text-[11px]">
                          {formatDate(log.timestamp)}
                        </td>

                        {/* Tier */}
                        <td className="px-4 py-3 whitespace-nowrap">
                          {isTier1 && (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">
                              Tier 1 (Regex)
                            </span>
                          )}
                          {isTier2 && (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                              Tier 2 (ML)
                            </span>
                          )}
                          {isTier3 && (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                              Tier 3 (LLM)
                            </span>
                          )}
                        </td>

                        {/* Category */}
                        <td className="px-4 py-3 whitespace-nowrap font-medium text-slate-200">
                          {log.category}
                        </td>

                        {/* Rule / Model */}
                        <td className="px-4 py-3 text-slate-400 font-mono text-[11px] max-w-xs truncate" title={log.rule_or_model}>
                          {log.rule_or_model}
                          {log.confidence !== undefined && log.confidence !== null && (
                            <span className="ml-1.5 text-slate-400">
                              ({(log.confidence * 100).toFixed(0)}%)
                            </span>
                          )}
                        </td>

                        {/* Action Taken */}
                        <td className="px-4 py-3 whitespace-nowrap">
                          <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
                            {log.action_taken}
                          </span>
                        </td>

                        {/* Redacted Excerpt */}
                        <td className="px-4 py-3 text-slate-400 font-mono text-[11px] max-w-xs truncate" title={log.message_excerpt}>
                          {log.message_excerpt}
                        </td>

                        {/* Status */}
                        <td className="px-4 py-3 whitespace-nowrap">
                          {log.resolved ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                              <CheckCircle2 className="size-3" /> Resolved
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                              <Clock className="size-3" /> Pending
                            </span>
                          )}
                        </td>

                        {/* Action Button */}
                        <td className="px-4 py-3 whitespace-nowrap text-right">
                          <button
                            type="button"
                            onClick={() => openReviewModal(log)}
                            className="rounded-lg bg-indigo-600/80 hover:bg-indigo-600 px-2.5 py-1 text-[11px] font-semibold text-white transition cursor-pointer"
                          >
                            Review
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 bg-slate-800/80 border-t border-slate-800 text-xs text-slate-400">
            <div>
              Showing {logs.length > 0 ? (page - 1) * limit + 1 : 0} to{" "}
              {Math.min(page * limit, total)} of {total} records
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((prev) => Math.max(1, prev - 1))}
                className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                <ChevronLeft className="size-3.5" /> Previous
              </button>
              <span className="px-2 font-medium text-slate-300">
                Page {page} of {totalPages}
              </span>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
                className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                Next <ChevronRight className="size-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Review & Resolution Modal */}
      {activeLog && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="review-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-xs"
        >
          <div className="w-full max-w-lg rounded-2xl border border-slate-700 bg-slate-800 p-6 shadow-2xl space-y-5 text-slate-100">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-700 pb-3">
              <div className="flex items-center gap-2.5">
                <FileText className="size-5 text-indigo-400" />
                <h3 id="review-modal-title" className="text-base font-bold text-white font-heading">
                  Review Crisis Event Record
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setActiveLog(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700 cursor-pointer"
                aria-label="Close dialog"
              >
                <X className="size-5" />
              </button>
            </div>

            {/* Modal Body / Record Metadata */}
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-2 bg-slate-900/60 p-3 rounded-xl border border-slate-800">
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase">Record ID</span>
                  <span className="font-mono text-slate-200">{activeLog.id}</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase">Logged At</span>
                  <span className="text-slate-200">{formatDate(activeLog.timestamp)}</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase">Detection Tier</span>
                  <span className="font-bold text-white">Tier {activeLog.tier}</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase">Category</span>
                  <span className="font-bold text-white">{activeLog.category}</span>
                </div>
                <div className="col-span-2">
                  <span className="text-slate-400 block text-[10px] uppercase">Rule / Model Fired</span>
                  <span className="font-mono text-slate-300">{activeLog.rule_or_model}</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase">Action Taken</span>
                  <span className="text-slate-300">{activeLog.action_taken}</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase">User Reference</span>
                  <span className="font-mono text-slate-300 truncate block">
                    {activeLog.user_id || "Anonymous"}
                  </span>
                </div>
              </div>

              {/* Redacted Message Excerpt */}
              <div>
                <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                  Redacted Triggering Utterance Excerpt
                </label>
                <div className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 font-mono text-slate-300 text-[11px]">
                  {activeLog.message_excerpt}
                </div>
                <p className="mt-1 text-[10px] text-slate-400">
                  Full message text was not stored to minimize sensitive user data retention.
                </p>
              </div>

              {/* Resolution Checkbox */}
              <div className="pt-2">
                <label className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={modalResolved}
                    onChange={(e) => setModalResolved(e.target.checked)}
                    className="size-4 rounded border-slate-600 bg-slate-900 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="text-xs font-semibold text-white">
                    Mark as Reviewed &amp; Resolved
                  </span>
                </label>
              </div>

              {/* Admin / Clinical Note Textarea */}
              <div>
                <label htmlFor="admin-note-input" className="block text-[11px] font-semibold text-slate-400 mb-1">
                  Clinician / Admin Audit Note
                </label>
                <textarea
                  id="admin-note-input"
                  rows={3}
                  value={modalAdminNote}
                  onChange={(e) => setModalAdminNote(e.target.value)}
                  placeholder="Record clinical observations, outcome verification, or false-positive notes..."
                  className="w-full rounded-xl border border-slate-700 bg-slate-900 p-2.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {updateSuccess && (
                <div className="p-2 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-xs flex items-center gap-1.5">
                  <CheckCircle2 className="size-4 shrink-0" />
                  <span>{updateSuccess}</span>
                </div>
              )}
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-700">
              <button
                type="button"
                onClick={() => setActiveLog(null)}
                className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700 cursor-pointer"
              >
                Close
              </button>
              <button
                type="button"
                disabled={isUpdating}
                onClick={handleSaveReview}
                className="rounded-xl bg-indigo-600 px-4 py-2 text-xs font-bold text-white transition hover:bg-indigo-500 disabled:opacity-50 cursor-pointer shadow-xs"
              >
                {isUpdating ? "Saving..." : "Save Review"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
