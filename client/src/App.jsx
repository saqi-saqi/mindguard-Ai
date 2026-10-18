import React, { useState, useEffect, useRef } from 'react';
import Navigation from './components/Navigation';
import ChatInterface from './components/ChatInterface';
import AnalyticsDashboard from './components/AnalyticsDashboard';
import AuthScreen from './components/AuthScreen';
import CrisisModal from './components/CrisisModal';
import SettingsPanel from './components/SettingsPanel';

export default function App() {
  const [activeTab, setActiveTab] = useState('auth');
  const [authMode, setAuthMode] = useState('login');
  const [user, setUser] = useState(null);
  const [token, setToken] = useState('');
  const [isCrisisModalOpen, setIsCrisisModalOpen] = useState(false);
  const [crisisResources, setCrisisResources] = useState(null);
  const [crisisMode, setCrisisMode] = useState('manual');
  const [safetyStatus, setSafetyStatus] = useState('');
  const [moodLogs, setMoodLogs] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [chatHistory, setChatHistory] = useState([]);
  const [chatKey, setChatKey] = useState(0);

  const handleNavigateToAuth = (mode = 'login') => {
    setAuthMode(mode);
    setActiveTab('auth');
  };

  // Clear previous session storage on clean startup so app always asks for login
  useEffect(() => {
    localStorage.removeItem('mg_token');
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

  // 2. Fetch User Persistent Mood Logs & Chat Sessions on Authentication
  const userId = user?.id ?? null;

  const fetchSessions = async () => {
    if (!token) return;
    try {
      const res = await fetch('/api/chat/sessions', {
        headers: { Authorization: `Bearer ${token}` }
      });
      const resData = await res.json().catch(() => null);
      if (res.ok && resData?.success !== false && resData?.data?.sessions) {
        setSessions(resData.data.sessions);
      }
    } catch (err) {
      console.error('Failed to fetch chat sessions:', err);
    }
  };

  useEffect(() => {
    if (!userId || !token) return;

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

    // Fetch user sessions list for the sidebar
    fetch('/api/chat/sessions', {
      headers: { Authorization: `Bearer ${token}` },
      signal
    })
      .then(async (res) => (res.ok ? res.json().catch(() => null) : null))
      .then((resData) => {
        if (resData && resData.success !== false && resData.data?.sessions) {
          setSessions(resData.data.sessions);
        }
      })
      .catch((err) => { if (err.name !== 'AbortError') console.error('Failed to fetch sessions:', err); });

    return () => controller.abort();
  }, [userId, token]);

  const handleLoginSuccess = (userData, userToken) => {
    setUser(userData);
    setToken(userToken);
    localStorage.setItem('mg_token', userToken);
    setActiveSessionId(null);
    setChatHistory([]);
    setChatKey((prev) => prev + 1);
    setActiveTab('chat');
  };

  const handleLogout = () => {
    setUser(null);
    setToken('');
    localStorage.removeItem('mg_token');
    setMoodLogs([]);
    setSessions([]);
    setActiveSessionId(null);
    setChatHistory([]);
    setChatKey((prev) => prev + 1);
    setActiveTab('auth');
  };

  const handleSelectSession = async (sessionId) => {
    setActiveSessionId(sessionId);
    setActiveTab('chat');
    if (!token) return;
    try {
      const res = await fetch(`/api/chat/history?session_id=${sessionId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const resData = await res.json().catch(() => null);
      if (res.ok && resData?.success !== false && resData?.data?.messages) {
        setChatHistory(resData.data.messages);
      } else {
        setChatHistory([]);
      }
      setChatKey((prev) => prev + 1);
    } catch (err) {
      console.error('Failed to load session messages:', err);
      setChatHistory([]);
      setChatKey((prev) => prev + 1);
    }
  };

  const handleNewChat = () => {
    setActiveSessionId(null);
    setChatHistory([]);
    setChatKey((prev) => prev + 1);
    setActiveTab('chat');
  };

  const handleDeleteSession = async (sessionId) => {
    if (!token) return;
    try {
      const res = await fetch(`/api/chat/sessions/${sessionId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setSessions((prev) => prev.filter((s) => s.id !== sessionId));
        if (activeSessionId === sessionId) {
          handleNewChat();
        }
      }
    } catch (err) {
      console.error('Failed to delete session:', err);
    }
  };

  const handleSessionCreated = (newSessionId) => {
    setActiveSessionId(newSessionId);
    fetchSessions();
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

  const handleClearMoodLogs = async () => {
    const confirmed = window.confirm(
      "Are you sure you want to clear your mood history?\n\n" +
      "This will remove your recorded mood check-ins and notes, while keeping your chat conversations intact."
    );
    if (!confirmed) return;

    if (!token) {
      setMoodLogs([]);
      return;
    }

    try {
      const res = await fetch('/api/moods', {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });
      const data = await res.json().catch(() => null);
      if (res.ok && data?.success !== false) {
        setMoodLogs([]);
      } else {
        const errMsg = data?.error?.message || "Failed to clear mood logs.";
        alert(`Error clearing mood logs: ${errMsg}`);
      }
    } catch (err) {
      console.error('Failed to clear mood logs:', err);
      alert("Network error clearing mood logs.");
    }
  };

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
      setSessions([]);
      setActiveSessionId(null);
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
        setSessions([]);
        setActiveSessionId(null);
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
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        onDeleteSession={handleDeleteSession}
      />

      {/* Main Dashboard Area */}
      <main className="relative flex-1 flex flex-col min-h-0 overflow-hidden" aria-hidden={isCrisisModalOpen || undefined}>
        {safetyStatus && (
          <div role="status" aria-live="polite" className="absolute left-1/2 top-3 z-20 w-[min(92%,680px)] -translate-x-1/2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-center text-xs font-medium text-emerald-900 shadow-lg">
            {safetyStatus}
            <button type="button" onClick={() => setSafetyStatus('')} className="ml-3 font-bold underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600">Dismiss</button>
          </div>
        )}
        <div className={`flex-1 flex flex-col min-h-0 ${activeTab === 'chat' ? '' : 'hidden'}`}>
          <ChatInterface
            key={`chat-instance-${chatKey}`}
            user={user}
            token={token}
            initialMessages={chatHistory}
            activeSessionId={activeSessionId}
            onOpenCrisisModal={handleOpenCrisisModal}
            onRecordMood={handleRecordMood}
            onWipePersonalData={handleWipePersonalData}
            onSessionCreated={handleSessionCreated}
            isCrisisModalOpen={isCrisisModalOpen}
          />
        </div>
        {activeTab === 'analytics' && (
          <AnalyticsDashboard
            moodLogs={moodLogs}
            onClearLogs={handleClearMoodLogs}
            token={token}
            user={user}
            onMoodCreated={handleRecordMood}
            onStartChat={() => setActiveTab('chat')}
            onNavigateToAuth={handleNavigateToAuth}
          />
        )}
        {activeTab === 'settings' && (
          <SettingsPanel
            user={user}
            token={token}
            onUpdated={handleSettingsUpdated}
            onAccountDeleted={handleAccountDeleted}
            onBackToChat={() => setActiveTab('chat')}
            onSignIn={() => handleNavigateToAuth('login')}
            onNavigateToAuth={handleNavigateToAuth}
          />
        )}
        {activeTab === 'auth' && (
          <AuthScreen
            key={`auth-${authMode}`}
            onLogin={handleLoginSuccess}
            defaultLoginMode={authMode === 'login'}
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
