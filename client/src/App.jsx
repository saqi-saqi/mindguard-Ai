import React, { useState, useEffect, useRef } from 'react';
import Navigation from './components/Navigation';
import ChatInterface from './components/ChatInterface';
import AnalyticsDashboard from './components/AnalyticsDashboard';
import AuthScreen from './components/AuthScreen';
import CrisisModal from './components/CrisisModal';
import SettingsPanel from './components/SettingsPanel';

export default function App() {
  const [activeTab, setActiveTab] = useState('chat');
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('mg_token') || '');
  const [isCrisisModalOpen, setIsCrisisModalOpen] = useState(false);
  const [crisisResources, setCrisisResources] = useState(null);
  const [crisisMode, setCrisisMode] = useState('manual');
  const [safetyStatus, setSafetyStatus] = useState('');
  const [moodLogs, setMoodLogs] = useState([]);
  const [chatHistory, setChatHistory] = useState([]);

  // 1. Restore User Session on Initial Page Load
  useEffect(() => {
    const savedToken = localStorage.getItem('mg_token');
    if (savedToken) {
      fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${savedToken}` }
      })
        .then(async (res) => (res.ok ? res.json().catch(() => null) : null))
        .then((resData) => {
          if (resData && resData.success !== false && resData.data?.user) {
            setUser(resData.data.user);
            setToken(savedToken);
          } else {
            localStorage.removeItem('mg_token');
            setToken('');
            setUser(null);
          }
        })
        .catch((err) => {
          console.error('Failed to restore session:', err);
        });
    }
  }, []);

  useEffect(() => {
    if (!token) return;
    fetch('/api/user/settings', { headers: { Authorization: `Bearer ${token}` } })
      .then(async (res) => (res.ok ? res.json().catch(() => null) : null))
      .then((resData) => {
        if (resData && resData.success !== false && resData.data?.settings) {
          setUser((current) => current ? { ...current, settings: resData.data.settings } : current);
        }
      })
      .catch((err) => console.error('Failed to fetch settings:', err));
  }, [token]);

  // 2. Fetch User Persistent Mood Logs & Chat History on Authentication
  //    Depend on user?.id (not user object) to avoid re-fetching when settings
  //    load and recreate the user object reference.
  const userId = user?.id ?? null;
  useEffect(() => {
    if (!userId || !token) return;

    // Cancel in-flight requests if this effect re-runs (React StrictMode guard)
    const controller = new AbortController();
    const { signal } = controller;

    fetch('/api/moods', {
      headers: { Authorization: `Bearer ${token}` },
      signal
    })
      .then(async (res) => (res.ok ? res.json().catch(() => null) : null))
      .then((resData) => {
        if (resData && resData.success !== false && resData.data?.mood_logs) {
          setMoodLogs(resData.data.mood_logs);
        }
      })
      .catch((err) => { if (err.name !== 'AbortError') console.error('Failed to fetch mood logs:', err); });

    fetch('/api/chat/history', {
      headers: { Authorization: `Bearer ${token}` },
      signal
    })
      .then(async (res) => (res.ok ? res.json().catch(() => null) : null))
      .then((resData) => {
        if (resData && resData.success !== false && resData.data?.messages) {
          setChatHistory(resData.data.messages);
        }
      })
      .catch((err) => { if (err.name !== 'AbortError') console.error('Failed to fetch chat history:', err); });

    return () => controller.abort();
  }, [userId, token]);

  const handleLoginSuccess = (userData, userToken) => {
    setUser(userData);
    setToken(userToken);
    localStorage.setItem('mg_token', userToken);
    setActiveTab('chat');
  };

  const handleLogout = () => {
    setUser(null);
    setToken('');
    localStorage.removeItem('mg_token');
    setMoodLogs([]);
    setChatHistory([]);
    setActiveTab('chat');
  };

  const handleOpenCrisisModal = (resources, mode = 'manual') => {
    setCrisisResources(resources);
    setCrisisMode(mode);
    setIsCrisisModalOpen(true);
  };

  const handleSafetyStatus = async (outcome) => {
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;
    try {
      await fetch('/api/safety-feedback', {
        method: 'POST',
        headers,
        body: JSON.stringify({ outcome, source: 'crisis_modal' })
      });
    } catch (err) {
      // Optional telemetry must never prevent access to urgent resources.
      console.warn('Could not record optional safety feedback:', err);
    }
    if (outcome === 'safe_for_now') {
      setSafetyStatus('Thanks for checking in. You can continue chatting, and urgent help remains available whenever you need it.');
    }
  };

  const handleRecordMood = (log) => {
    setMoodLogs((prev) => [...prev, log]);
  };

  const handleSettingsUpdated = (settings, trustedContact, safetyProfile) => {
    setUser((current) => current ? { ...current, settings, trusted_contact: trustedContact || current.trusted_contact, safety_profile: safetyProfile || current.safety_profile } : current);
  };

  const handleAccountDeleted = () => handleLogout();

  const handleWipePersonalData = async () => {
    const confirmed = window.confirm(
      "Are you sure you want to delete your chat and mood history?\n\n" +
      "This action will permanently delete:\n" +
      "• All saved chat messages & reflection sessions\n" +
      "• All recorded mood entries & notes\n" +
      "• All stored analytics metrics\n\n" +
      "This action cannot be undone."
    );
    if (!confirmed) return;

    if (!token) {
      setMoodLogs([]);
      setChatHistory([]);
      return;
    }

    try {
      const res = await fetch('/api/user/data', {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });
      const data = await res.json().catch(() => null);
      if (res.ok && data?.success !== false) {
        setMoodLogs([]);
        setChatHistory([]);
        alert("Your chat and mood history have been permanently deleted.");
      } else {
        const errMsg = data?.error?.message || "Failed to delete history on server. State retained.";
        alert(`Error deleting history: ${errMsg}`);
      }
    } catch (err) {
      console.error('Failed to delete personal data:', err);
      alert(`Network error deleting history: ${err.message || err}. State retained.`);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col md:flex-row font-sans">
      {/* Responsive Sidebar Navigation & Mobile Drawer */}
      <Navigation
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        user={user}
        onLogout={handleLogout}
        onOpenCrisisModal={() => handleOpenCrisisModal(null, 'manual')}
      />

      {/* Main Dashboard Area */}
      <main className="relative flex-1 flex flex-col min-h-0 overflow-hidden" aria-hidden={isCrisisModalOpen || undefined}>
        {safetyStatus && (
          <div role="status" aria-live="polite" className="absolute left-1/2 top-3 z-20 w-[min(92%,680px)] -translate-x-1/2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-center text-xs font-medium text-emerald-900 shadow-lg">
            {safetyStatus}
            <button type="button" onClick={() => setSafetyStatus('')} className="ml-3 font-bold underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600">Dismiss</button>
          </div>
        )}
        {activeTab === 'chat' && (
          <ChatInterface
            user={user}
            token={token}
            initialMessages={chatHistory}
            onOpenCrisisModal={handleOpenCrisisModal}
            onRecordMood={handleRecordMood}
            onWipePersonalData={handleWipePersonalData}
          />
        )}
        {activeTab === 'analytics' && (
          <AnalyticsDashboard
            moodLogs={moodLogs}
            onClearLogs={handleWipePersonalData}
            token={token}
            onMoodCreated={handleRecordMood}
            onStartChat={() => setActiveTab('chat')}
          />
        )}
        {activeTab === 'settings' && user && (
          <SettingsPanel
            user={user}
            token={token}
            onUpdated={handleSettingsUpdated}
            onAccountDeleted={handleAccountDeleted}
          />
        )}
        {activeTab === 'auth' && (
          <AuthScreen
            onLogin={handleLoginSuccess}
          />
        )}
      </main>

      {/* High-Risk Emergency Crisis Modal */}
      <CrisisModal
        isOpen={isCrisisModalOpen}
        onClose={() => setIsCrisisModalOpen(false)}
        resources={crisisResources}
        trustedContact={user?.trusted_contact}
        safetyProfile={user?.safety_profile}
        mode={crisisMode}
        onSafetyStatus={handleSafetyStatus}
      />
    </div>
  );
}
