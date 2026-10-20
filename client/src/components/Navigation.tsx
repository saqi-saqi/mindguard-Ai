import { useState, useEffect } from "react";
import {
  MessageSquare,
  BarChart2,
  ShieldAlert,
  User,
  Settings,
  LogOut,
  HeartHandshake,
  Menu,
  X,
  Plus,
  Trash2,
} from "lucide-react";
import type { MindUser, Tab, ChatSession } from "./types";

interface NavigationProps {
  activeTab: Tab;
  setActiveTab: (tab: Tab) => void;
  user: MindUser | null;
  onLogout: () => void;
  onOpenCrisisModal: () => void;
  sessions?: ChatSession[];
  activeSessionId?: string | null;
  onSelectSession?: (sessionId: string) => void;
  onNewChat?: () => void;
  onDeleteSession?: (sessionId: string) => void;
}

const NAV_ITEMS: { id: Tab; label: string; icon: typeof MessageSquare }[] = [
  { id: "chat", label: "AI Chat Assistant", icon: MessageSquare },
  { id: "analytics", label: "Mood & Analytics", icon: BarChart2 },
  { id: "settings", label: "Privacy & Settings", icon: Settings },
];

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-indigo-600 text-white shadow-xs">
        <HeartHandshake className={compact ? "size-5" : "size-5"} />
      </div>
      <div className="min-w-0">
        <p className="truncate text-base font-bold leading-tight text-white font-heading">
          MindGuard
        </p>
        <p className="truncate text-[11px] font-medium text-slate-400">
          AI Mental Health Support
        </p>
      </div>
    </div>
  );
}

function SidebarBody({
  activeTab,
  onSelect,
  user,
  onLogout,
  onCrisis,
  sessions = [],
  activeSessionId = null,
  onSelectSession,
  onNewChat,
  onDeleteSession,
}: {
  activeTab: Tab;
  onSelect: (tab: Tab) => void;
  user: MindUser | null;
  onLogout: () => void;
  onCrisis: () => void;
  sessions?: ChatSession[];
  activeSessionId?: string | null;
  onSelectSession?: (sessionId: string) => void;
  onNewChat?: () => void;
  onDeleteSession?: (sessionId: string) => void;
}) {
  return (
    <div className="flex flex-col flex-1 min-h-0 gap-3">
      {/* New Chat Primary Action Button */}
      <button
        type="button"
        onClick={() => {
          onNewChat?.();
          onSelect("chat");
        }}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-3 py-2.5 text-xs font-bold text-white shadow-xs transition-colors hover:bg-indigo-500 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
      >
        <Plus className="size-4 shrink-0" />
        <span>New Chat</span>
      </button>

      {/* Primary Navigation */}
      <nav aria-label="Primary navigation" className="flex flex-col gap-1 shrink-0">
        <p className="px-3 pb-1 text-[10px] font-bold uppercase tracking-widest text-slate-400">
          Navigation
        </p>
        {NAV_ITEMS.map((item) => {
          const active = activeTab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelect(item.id)}
              aria-current={active ? "page" : undefined}
              className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-xs font-semibold transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900 ${
                active
                  ? "bg-indigo-600 text-white shadow-xs font-bold"
                  : "text-slate-300 hover:bg-slate-800/80 hover:text-white"
              }`}
            >
              <item.icon className="size-4 shrink-0" />
              <span className="truncate">{item.label}</span>
            </button>
          );
        })}

        <button
          type="button"
          onClick={() => onSelect("admin")}
          aria-current={activeTab === "admin" ? "page" : undefined}
          className={`flex w-full items-center justify-between rounded-xl px-3 py-2 text-xs font-semibold transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900 ${
            activeTab === "admin"
              ? "bg-rose-600 text-white shadow-xs font-bold"
              : user?.role === "admin"
              ? "text-rose-300 hover:bg-rose-500/10 hover:text-white"
              : "text-slate-400 hover:bg-slate-800/80 hover:text-slate-200"
          }`}
        >
          <div className="flex items-center gap-3 truncate">
            <ShieldAlert className={`size-4 shrink-0 ${activeTab === "admin" ? "text-white" : user?.role === "admin" ? "text-rose-400" : "text-slate-400"}`} />
            <span className="truncate">Review Safety Logs</span>
          </div>
          <span
            className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase tracking-wider ${
              user?.role === "admin"
                ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                : "bg-slate-800 text-slate-400 border border-slate-700"
            }`}
          >
            Admin
          </span>
        </button>

        <button
          type="button"
          onClick={onCrisis}
          className="mt-1 flex w-full items-center gap-3 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs font-semibold text-rose-200 transition-colors hover:bg-rose-500/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900 cursor-pointer"
        >
          <ShieldAlert className="size-4 shrink-0 text-rose-400" />
          <span className="truncate">Emergency Helpline</span>
        </button>
      </nav>

      {/* ChatGPT-style Recent Chats Section */}
      {user && sessions.length > 0 && (
        <div className="flex flex-col min-h-0 flex-1 border-t border-slate-800/70 pt-2">
          <div className="flex items-center justify-between px-3 pb-1.5 text-[10px] font-bold uppercase tracking-widest text-slate-400 shrink-0">
            <span>Recent Chats</span>
            <span className="text-[10px] text-slate-500 font-normal">({sessions.length})</span>
          </div>
          <div className="overflow-y-auto space-y-1 pr-1 flex-1 min-h-0">
            {sessions.map((ses) => {
              const isCurrent = activeTab === "chat" && activeSessionId === ses.id;
              return (
                <div
                  key={ses.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => {
                    onSelectSession?.(ses.id);
                    onSelect("chat");
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelectSession?.(ses.id);
                      onSelect("chat");
                    }
                  }}
                  className={`group flex items-center justify-between rounded-xl px-2.5 py-1.5 text-xs transition-colors cursor-pointer ${
                    isCurrent
                      ? "bg-slate-800 text-white font-medium border border-indigo-500/40 shadow-2xs"
                      : "text-slate-300 hover:bg-slate-800/60 hover:text-white"
                  }`}
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <MessageSquare className={`size-3.5 shrink-0 ${isCurrent ? "text-indigo-400" : "text-slate-400 group-hover:text-indigo-400"}`} />
                    <span className="truncate max-w-[145px]" title={ses.title}>
                      {ses.title || "Chat reflection"}
                    </span>
                  </div>
                  {onDeleteSession && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteSession(ses.id);
                      }}
                      title="Delete this chat"
                      aria-label={`Delete chat ${ses.title}`}
                      className="opacity-0 group-hover:opacity-100 rounded p-1 text-slate-400 hover:bg-rose-500/20 hover:text-rose-300 transition-all focus:opacity-100 cursor-pointer"
                    >
                      <Trash2 className="size-3" />
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* User Session Footer */}
      <div className="mt-auto border-t border-slate-800/80 pt-3 shrink-0">
        {user ? (
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-xl border border-slate-800 bg-slate-800/50 p-2">
            <div className="flex min-w-0 items-center gap-2.5">
              <div className="grid size-7 shrink-0 place-items-center rounded-full bg-indigo-600 text-xs font-bold text-white">
                {(user.name || user.email || "U").charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0">
                <p className="truncate text-xs font-semibold text-white">{user.name || user.email || "User"}</p>
                <p className="truncate text-[11px] text-slate-400">{user.email || ""}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={onLogout}
              aria-label="Log out"
              title="Log out"
              className="grid size-7 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-rose-500/10 hover:text-rose-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400 cursor-pointer"
            >
              <LogOut className="size-3.5" />
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => onSelect("auth")}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 py-2.5 text-xs font-semibold text-white transition-colors hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 cursor-pointer"
          >
            <User className="size-4" />
            <span>Sign In / Register</span>
          </button>
        )}
      </div>
    </div>
  );
}

export default function Navigation({
  activeTab,
  setActiveTab,
  user,
  onLogout,
  onOpenCrisisModal,
  sessions = [],
  activeSessionId = null,
  onSelectSession,
  onNewChat,
  onDeleteSession,
}: NavigationProps) {
  const [isMobileOpen, setIsMobileOpen] = useState(false);

  // Lock body scroll when mobile drawer is open
  useEffect(() => {
    if (isMobileOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isMobileOpen]);

  const handleTabClick = (tab: Tab) => {
    setActiveTab(tab);
    setIsMobileOpen(false);
  };

  const handleCrisisClick = () => {
    onOpenCrisisModal();
    setIsMobileOpen(false);
  };

  const handleLogout = () => {
    onLogout();
    setIsMobileOpen(false);
  };

  const handleSelectSession = (id: string) => {
    onSelectSession?.(id);
    setIsMobileOpen(false);
  };

  const handleNewChat = () => {
    onNewChat?.();
    setIsMobileOpen(false);
  };

  return (
    <>
      {/* Mobile Header */}
      <header className="sticky top-0 z-40 flex items-center justify-between gap-3 border-b border-slate-800/80 bg-slate-900 px-4 py-3 md:hidden">
        <Brand compact />
        <button
          type="button"
          onClick={() => setIsMobileOpen(true)}
          aria-label="Open navigation menu"
          aria-expanded={isMobileOpen}
          className="grid size-10 shrink-0 place-items-center rounded-xl text-slate-300 transition-colors hover:bg-slate-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 cursor-pointer"
        >
          <Menu className="size-5" />
        </button>
      </header>

      {/* Mobile Drawer */}
      {isMobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            aria-label="Close navigation menu"
            onClick={() => setIsMobileOpen(false)}
            className="absolute inset-0 bg-slate-950/75 backdrop-blur-xs"
          />
          <div className="fade-in absolute inset-y-0 left-0 flex w-[260px] max-w-[85vw] flex-col gap-4 border-r border-slate-800 bg-slate-900 p-4 shadow-2xl h-full">
            <div className="flex items-center justify-between gap-2 shrink-0">
              <Brand compact />
              <button
                type="button"
                onClick={() => setIsMobileOpen(false)}
                aria-label="Close navigation menu"
                className="grid size-8 shrink-0 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-slate-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 cursor-pointer"
              >
                <X className="size-4" />
              </button>
            </div>
            <SidebarBody
              activeTab={activeTab}
              onSelect={handleTabClick}
              user={user}
              onLogout={handleLogout}
              onCrisis={handleCrisisClick}
              sessions={sessions}
              activeSessionId={activeSessionId}
              onSelectSession={handleSelectSession}
              onNewChat={handleNewChat}
              onDeleteSession={onDeleteSession}
            />
          </div>
        </div>
      )}

      {/* Desktop Fixed Sidebar */}
      <aside className="sticky top-0 z-30 hidden h-screen w-[260px] shrink-0 flex-col gap-4 border-r border-slate-800/80 bg-slate-900 p-4 text-slate-100 md:flex">
        <Brand />
        <SidebarBody
          activeTab={activeTab}
          onSelect={setActiveTab}
          user={user}
          onLogout={onLogout}
          onCrisis={onOpenCrisisModal}
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelectSession={onSelectSession}
          onNewChat={onNewChat}
          onDeleteSession={onDeleteSession}
        />
      </aside>
    </>
  );
}
