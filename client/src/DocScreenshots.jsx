import React from 'react';
import Navigation from './components/Navigation';
import ChatInterface from './components/ChatInterface';
import AnalyticsDashboard from './components/AnalyticsDashboard';
import AuthScreen from './components/AuthScreen';
import CrisisModal from './components/CrisisModal';
import SettingsPanel from './components/SettingsPanel';

export default function DocScreenshots() {
  const params = new URLSearchParams(window.location.search);
  const screen = params.get('screen') || 'login';

  const mockUser = {
    id: 'usr-demo123456',
    name: 'Saqib Tariq',
    email: 'saqib@qau.edu.pk',
    role: 'user',
    created_at: '2026-08-01T10:00:00Z',
    settings: {
      consent_given: true,
      retention_enabled: true,
      retention_days: 30,
      locale: 'pakistan',
    },
    trusted_contact: {
      name: 'Dr. Ali',
      phone: '+92 300 1234567',
      relationship: 'Doctor / Counselor',
    },
  };

  const mockMoodLogs = [
    { id: 'm1', score: 7, tags: ['Calm', 'Productive'], notes: 'Finished the assignment on time.', created_at: '2026-08-23T14:30:00Z' },
    { id: 'm2', score: 5, tags: ['Tired', 'Work'], notes: 'Busy workday, feeling slight pressure.', created_at: '2026-08-22T18:00:00Z' },
    { id: 'm3', score: 8, tags: ['Happy', 'Social'], notes: 'Met friends after classes.', created_at: '2026-08-21T20:15:00Z' },
    { id: 'm4', score: 6, tags: ['Neutral', 'Sleep'], notes: 'Restful sleep, feeling centered.', created_at: '2026-08-20T09:00:00Z' },
    { id: 'm5', score: 7, tags: ['Focused'], notes: 'Made good progress on project.', created_at: '2026-08-19T16:00:00Z' },
  ];

  const mockResources = {
    region: 'pakistan',
    resources: {
      pakistan: [
        { name: 'Umang Mental Health Helpline', contact: '0311-7786264', hours: '24/7 Free Support', available: true },
        { name: 'Rozan Counseling Helpline', contact: '0800-22444', hours: 'Mon-Sat 9AM-5PM', available: true },
        { name: 'Emergency Rescue Services', contact: '1122', hours: '24/7 Immediate Response', available: true },
      ],
      international: [
        { name: '988 Suicide & Crisis Lifeline (US/CA)', contact: 'Call/Text 988', hours: '24/7 Free & Confidential', available: true },
        { name: 'Befrienders Worldwide', contact: 'www.befrienders.org', hours: 'Global Helplines Directory', available: true },
      ]
    }
  };

  const mockChatMessages = [
    {
      id: 'msg-1',
      sender: 'user',
      text: "I've been feeling really overwhelmed with exams and final project deadlines lately.",
      timestamp: '10:30 AM',
    },
    {
      id: 'msg-2',
      sender: 'bot',
      text: "It is completely understandable to feel overwhelmed when multiple deadlines pile up. Remember to give yourself credit for how hard you've been working.\n\nLet's take a slow breath together. Would you like to **break down what's on your plate** into small, manageable steps, or try a **quick 2-minute grounding exercise** first?",
      sentiment: 'NEGATIVE',
      intent: 'academic_stress',
      emotion: 'anxiety',
      timestamp: '10:31 AM',
    },
    {
      id: 'msg-3',
      sender: 'user',
      text: 'Breaking it down into smaller steps sounds helpful. Where should we start?',
      timestamp: '10:33 AM',
    },
    {
      id: 'msg-4',
      sender: 'bot',
      text: "Great choice! Let's pick just **one single priority task** for today. What is the one thing that would give you the most relief once it's done?\n\nOnce we identify it, we'll outline just the very first 15-minute action step.",
      sentiment: 'POSITIVE',
      intent: 'coping_strategy',
      emotion: 'hope',
      timestamp: '10:34 AM',
    }
  ];

  if (screen === 'login') {
    return (
      <div className="h-screen bg-slate-50 flex flex-col font-sans">
        <AuthScreen onLogin={() => {}} defaultLoginMode={true} />
      </div>
    );
  }

  if (screen === 'signup') {
    return (
      <div className="h-screen bg-slate-50 flex flex-col font-sans">
        <AuthScreen onLogin={() => {}} defaultLoginMode={false} />
      </div>
    );
  }

  if (screen === 'chat') {
    return (
      <div className="h-screen bg-slate-900 text-slate-100 flex flex-row font-sans overflow-hidden">
        <Navigation
          activeTab="chat"
          setActiveTab={() => {}}
          user={mockUser}
          onLogout={() => {}}
          onOpenCrisisModal={() => {}}
        />
        <main className="relative flex-1 flex flex-col min-h-0 overflow-hidden bg-slate-50 text-slate-900">
          <ChatInterface
            user={mockUser}
            token="demo-jwt-token"
            initialMessages={mockChatMessages}
            onOpenCrisisModal={() => {}}
            onRecordMood={() => {}}
          />
        </main>
      </div>
    );
  }

  if (screen === 'crisis') {
    return (
      <div className="h-screen bg-slate-900 text-slate-100 flex flex-row font-sans overflow-hidden">
        <Navigation
          activeTab="chat"
          setActiveTab={() => {}}
          user={mockUser}
          onLogout={() => {}}
          onOpenCrisisModal={() => {}}
        />
        <main className="relative flex-1 flex flex-col min-h-0 overflow-hidden bg-slate-50 text-slate-900">
          <ChatInterface
            user={mockUser}
            token="demo-jwt-token"
            initialMessages={mockChatMessages}
            onOpenCrisisModal={() => {}}
            onRecordMood={() => {}}
          />
        </main>
        <CrisisModal
          isOpen={true}
          onClose={() => {}}
          resources={mockResources}
          onSafetyStatus={() => {}}
          mode="auto"
          trustedContact={mockUser.trusted_contact}
        />
      </div>
    );
  }

  if (screen === 'mood') {
    return (
      <div className="h-screen bg-slate-900 text-slate-100 flex flex-row font-sans overflow-hidden">
        <Navigation
          activeTab="analytics"
          setActiveTab={() => {}}
          user={mockUser}
          onLogout={() => {}}
          onOpenCrisisModal={() => {}}
        />
        <main className="relative flex-1 flex flex-col min-h-0 overflow-y-auto bg-slate-50 text-slate-900 p-6">
          <div className="max-w-4xl w-full mx-auto">
            <AnalyticsDashboard
              moodLogs={mockMoodLogs}
              onMoodCreated={() => {}}
            />
          </div>
        </main>
      </div>
    );
  }

  if (screen === 'analytics') {
    return (
      <div className="h-screen bg-slate-900 text-slate-100 flex flex-row font-sans overflow-hidden">
        <Navigation
          activeTab="analytics"
          setActiveTab={() => {}}
          user={mockUser}
          onLogout={() => {}}
          onOpenCrisisModal={() => {}}
        />
        <main className="relative flex-1 flex flex-col min-h-0 overflow-y-auto bg-slate-50 text-slate-900 p-6">
          <div className="max-w-4xl w-full mx-auto">
            <AnalyticsDashboard
              moodLogs={mockMoodLogs}
              onMoodCreated={() => {}}
            />
          </div>
        </main>
      </div>
    );
  }

  if (screen === 'settings') {
    return (
      <div className="h-screen bg-slate-900 text-slate-100 flex flex-row font-sans overflow-hidden">
        <Navigation
          activeTab="settings"
          setActiveTab={() => {}}
          user={mockUser}
          onLogout={() => {}}
          onOpenCrisisModal={() => {}}
        />
        <main className="relative flex-1 flex flex-col min-h-0 overflow-y-auto bg-slate-50 text-slate-900 p-6">
          <div className="max-w-3xl w-full mx-auto">
            <SettingsPanel
              user={mockUser}
              token="demo-jwt-token"
              onUpdated={() => {}}
              onAccountDeleted={() => {}}
            />
          </div>
        </main>
      </div>
    );
  }

  return <div>Unknown screen</div>;
}
