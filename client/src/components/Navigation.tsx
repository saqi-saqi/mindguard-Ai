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
} from "lucide-react";
import type { MindUser, Tab } from "./types";

interface NavigationProps {
  activeTab: Tab;
  setActiveTab: (tab: Tab) => void;
  user: MindUser | null;
  onLogout: () => void;
  onOpenCrisisModal: () => void;
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
}: {
  activeTab: Tab;
  onSelect: (tab: Tab) => void;
  user: MindUser | null;
  onLogout: () => void;
  onCrisis: () => void;
}) {
  return (
    <>
      <nav aria-label="Primary navigation" className="flex flex-col gap-1">
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
              className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-xs font-semibold transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900 ${
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
          onClick={onCrisis}
          className="mt-2 flex w-full items-center gap-3 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2.5 text-xs font-semibold text-rose-200 transition-colors hover:bg-rose-500/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900 cursor-pointer"
        >
          <ShieldAlert className="size-4 shrink-0 text-rose-400" />
          <span className="truncate">Emergency Helpline</span>
        </button>
      </nav>

      <div className="mt-auto border-t border-slate-800/80 pt-4">
        {user ? (
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-xl border border-slate-800 bg-slate-800/50 p-2.5">
            <div className="flex min-w-0 items-center gap-2.5">
              <div className="grid size-8 shrink-0 place-items-center rounded-full bg-indigo-600 text-xs font-bold text-white">
                {user.name.charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0">
                <p className="truncate text-xs font-semibold text-white">{user.name}</p>
                <p className="truncate text-[11px] text-slate-400">{user.email}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={onLogout}
              aria-label="Log out"
              title="Log out"
              className="grid size-8 shrink-0 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-rose-500/10 hover:text-rose-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400 cursor-pointer"
            >
              <LogOut className="size-4" />
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
    </>
  );
}

export default function Navigation({
  activeTab,
  setActiveTab,
  user,
  onLogout,
  onOpenCrisisModal,
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
          <div className="fade-in absolute inset-y-0 left-0 flex w-[260px] max-w-[85vw] flex-col gap-5 border-r border-slate-800 bg-slate-900 p-5 shadow-2xl">
            <div className="flex items-center justify-between gap-2">
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
            />
          </div>
        </div>
      )}

      {/* Desktop Fixed Sidebar */}
      <aside className="sticky top-0 z-30 hidden h-screen w-[250px] shrink-0 flex-col gap-5 border-r border-slate-800/80 bg-slate-900 p-4 text-slate-100 md:flex">
        <Brand />
        <SidebarBody
          activeTab={activeTab}
          onSelect={setActiveTab}
          user={user}
          onLogout={onLogout}
          onCrisis={onOpenCrisisModal}
        />
      </aside>
    </>
  );
}
