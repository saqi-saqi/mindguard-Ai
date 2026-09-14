import { useState } from "react";
import { Shield, Database, Phone, Download, Trash2, AlertOctagon, CheckCircle2, Eye, EyeOff, Lock, AlertCircle, Info, Building2 } from "lucide-react";
import type { MindUser, SafetyProfile, TrustedContact, UserSettings } from "./types";

interface Props {
  user: MindUser;
  token: string;
  onUpdated: (settings: UserSettings, trustedContact?: TrustedContact, safetyProfile?: SafetyProfile) => void;
  onAccountDeleted: () => void;
}

const defaults: UserSettings = {
  consent_given: false,
  retention_enabled: true,
  retention_days: 30,
  locale: "pakistan"
};

const safetyProfileDefaults: SafetyProfile = {
  preferred_hospital_name: "",
  preferred_hospital_phone: "",
  city_or_district: "",
  emergency_actions_consent: false,
};

export default function SettingsPanel({ user, token, onUpdated, onAccountDeleted }: Props) {
  const [settings, setSettings] = useState<UserSettings>(user.settings || defaults);
  const [contact, setContact] = useState<TrustedContact>(
    user.trusted_contact || { name: "", phone: "", relationship: "Friend or family" }
  );
  const [safetyProfile, setSafetyProfile] = useState<SafetyProfile>({
    ...safetyProfileDefaults,
    ...(user.safety_profile || {})
  });
  const [maskPhone, setMaskPhone] = useState(true);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const maskPhoneNumber = (num: string) => {
    if (!num) return "";
    const clean = num.trim();
    if (clean.length <= 4) return "••••";
    const visibleStart = clean.slice(0, 3);
    const visibleEnd = clean.slice(-3);
    return `${visibleStart} ••• ••• ${visibleEnd}`;
  };

  const showNotification = (text: string, type: "success" | "error" = "success") => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 5000);
  };

  const save = async () => {
    setIsSaving(true);
    setMessage(null);
    try {
      const response = await fetch("/api/user/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(settings)
      });
      let result: any = null;
      try {
        result = await response.json();
      } catch {
        if (!response.ok) throw new Error(`Server error (${response.status}): Backend server is unreachable.`);
        throw new Error("Invalid response from server.");
      }
      if (!response.ok || result.success === false) {
        throw new Error(result?.error?.message || "Could not save settings.");
      }

      let trustedContact = user.trusted_contact;
      const contactResponse = await fetch("/api/user/trusted-contact", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(contact)
      });
      let contactResult: any = null;
      try {
        contactResult = await contactResponse.json();
      } catch {
        if (!contactResponse.ok) throw new Error(`Server error (${contactResponse.status}): Could not save trusted contact.`);
        throw new Error("Invalid response from server.");
      }
      if (!contactResponse.ok || contactResult.success === false) {
        throw new Error(contactResult?.error?.message || "Could not save trusted contact.");
      }
      trustedContact = contactResult.data?.user?.trusted_contact;

      const profileResponse = await fetch("/api/user/safety-profile", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(safetyProfile)
      });
      const profileResult = await profileResponse.json().catch(() => null);
      if (!profileResponse.ok || profileResult?.success === false) {
        throw new Error(profileResult?.error?.message || "Could not save safety profile.");
      }

      onUpdated(result.data.settings, trustedContact, profileResult.data?.safety_profile);
      showNotification("Settings and privacy preferences updated successfully.", "success");
    } catch (err) {
      showNotification((err as Error).message, "error");
    } finally {
      setIsSaving(false);
    }
  };

  const downloadExport = async () => {
    setMessage(null);
    try {
      const response = await fetch("/api/user/export", {
        headers: { Authorization: `Bearer ${token}` }
      });
      let result: any = null;
      try {
        result = await response.json();
      } catch {
        if (!response.ok) throw new Error(`Server error (${response.status}): Could not export data.`);
        throw new Error("Invalid response from server.");
      }
      if (!response.ok || result.success === false) {
        throw new Error(result?.error?.message || "Could not export data.");
      }
      const blob = new Blob([JSON.stringify(result.data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "mindguard-data-export.json";
      link.click();
      URL.revokeObjectURL(url);
      showNotification("Personal data export downloaded successfully.", "success");
    } catch (err) {
      showNotification((err as Error).message, "error");
    }
  };

  const executeAccountDeletion = async () => {
    if (deleteConfirmText.trim().toUpperCase() !== "DELETE") return;
    setIsDeleting(true);
    try {
      const response = await fetch("/api/auth/account", {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      let result: any = null;
      try {
        result = await response.json();
      } catch {
        if (!response.ok) throw new Error(`Server error (${response.status}): Could not delete account.`);
        throw new Error("Invalid response from server.");
      }
      if (!response.ok || result.success === false) {
        throw new Error(result?.error?.message || "Could not delete account.");
      }
      setShowDeleteModal(false);
      onAccountDeleted();
    } catch (err) {
      showNotification((err as Error).message, "error");
      setIsDeleting(false);
    }
  };

  const inputClass =
    "mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400";

  return (
    <section className="min-h-0 flex-1 overflow-y-auto bg-slate-50 p-4 sm:p-8 font-sans" aria-label="Privacy and settings">
      <div className="mx-auto max-w-2xl space-y-6">
        {/* Header */}
        <div className="border-b border-slate-200/90 pb-4">
          <h1 className="text-xl font-bold text-slate-900 font-heading sm:text-2xl">
            Privacy &amp; Settings
          </h1>
          <p className="mt-0.5 text-xs text-slate-600 sm:text-sm font-normal">
            Manage your consent choices, automated retention rules, emergency contacts, and data sovereignty.
          </p>
        </div>

        {message && (
          <div
            role="status"
            aria-live="polite"
            className={`flex items-center gap-2 rounded-xl border p-3 text-xs font-semibold shadow-2xs ${
              message.type === "success"
                ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                : "border-rose-200 bg-rose-50 text-rose-900"
            }`}
          >
            {message.type === "success" ? (
              <CheckCircle2 className="size-4 text-emerald-600 shrink-0" />
            ) : (
              <AlertCircle className="size-4 text-rose-600 shrink-0" />
            )}
            <span>{message.text}</span>
          </div>
        )}

        {/* Data Transparency Card */}
        <div className="rounded-2xl border border-indigo-100 bg-indigo-50/70 p-4 text-xs text-indigo-950 shadow-2xs space-y-2">
          <div className="flex items-center gap-2 font-bold font-heading text-indigo-900">
            <Info className="size-4 text-indigo-600 shrink-0" />
            <span>What MindGuard Stores &amp; Why</span>
          </div>
          <ul className="list-disc list-inside space-y-1 text-slate-700 font-normal pl-1">
            <li><strong>Chat messages:</strong> Retained temporarily for multi-turn conversational context when retention is enabled.</li>
            <li><strong>Mood check-ins:</strong> Saved for your personal self-reflection trend charts.</li>
            <li><strong>Designated emergency contact:</strong> Stored locally in your profile for fast manual access during high distress.</li>
            <li><strong>Account credentials:</strong> Salted &amp; hashed for secure authentication.</li>
          </ul>
        </div>

        {/* Privacy & Retention Controls */}
        <div className="space-y-4 rounded-2xl border border-slate-200/90 bg-white p-5 shadow-2xs">
          <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
            <Shield className="size-4 text-indigo-600" />
            <h2 className="text-sm font-bold text-slate-900 font-heading">Data Retention &amp; Storage Preferences</h2>
          </div>

          <label className="flex items-start gap-3 text-xs text-slate-800 cursor-pointer">
            <input
              type="checkbox"
              checked={settings.consent_given}
              onChange={(e) => setSettings({ ...settings, consent_given: e.target.checked })}
              className="mt-0.5 size-4 accent-indigo-600 rounded cursor-pointer"
            />
            <span>
              <strong className="font-semibold text-slate-900">Consent to process sensitive self-help text</strong>
              <br />
              <span className="text-slate-600 font-normal">
                MindGuard provides non-clinical self-help support and risk identification, not licensed therapy or medical advice.
              </span>
            </span>
          </label>

          <label className="flex items-start gap-3 text-xs text-slate-800 cursor-pointer">
            <input
              type="checkbox"
              checked={settings.retention_enabled}
              onChange={(e) => setSettings({ ...settings, retention_enabled: e.target.checked })}
              className="mt-0.5 size-4 accent-indigo-600 rounded cursor-pointer"
            />
            <span>
              <strong className="font-semibold text-slate-900">Retain authenticated chat history and mood entries</strong>
              <br />
              <span className="text-slate-600 font-normal">
                Disabling retention stops saving new conversation records. Past records remain subject to the retention window.
              </span>
            </span>
          </label>

          <div className="grid grid-cols-1 gap-3 pt-2">
            <div>
              <label htmlFor="retention-days" className="block text-xs font-semibold text-slate-800">
                Retention Window (Days: 1–365)
              </label>
              <input
                id="retention-days"
                className={inputClass}
                type="number"
                min="1"
                max="365"
                value={settings.retention_days}
                disabled={!settings.retention_enabled}
                onChange={(e) => setSettings({ ...settings, retention_days: Number(e.target.value) })}
              />
              <p className="text-[11px] text-slate-500 mt-1">
                Records older than {settings.retention_days} days are automatically purged.
              </p>
            </div>

          </div>
          <p className="rounded-xl border border-indigo-100 bg-indigo-50 px-3 py-2 text-[11px] text-indigo-900">
            Emergency resources are configured for Pakistan: Rescue 1122, Police 15, and local support services.
          </p>
        </div>

        {/* Optional Hospital & Safety Preferences */}
        <div className="space-y-3 rounded-2xl border border-slate-200/90 bg-white p-5 shadow-2xs">
          <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
            <Building2 className="size-4 text-indigo-600" />
            <h2 className="text-sm font-bold text-slate-900 font-heading">Optional Hospital &amp; Safety Preferences</h2>
          </div>
          <p className="text-xs leading-relaxed text-slate-600">
            Save a preferred hospital only if it would help you act quickly in an emergency. MindGuard does not share this information or contact a hospital, police, or anyone else automatically.
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label htmlFor="safety-city" className="block text-xs font-semibold text-slate-700">City or District (optional)</label>
              <input id="safety-city" className={inputClass} placeholder="e.g. Lahore" value={safetyProfile.city_or_district} onChange={(e) => setSafetyProfile({ ...safetyProfile, city_or_district: e.target.value })} />
            </div>
            <div>
              <label htmlFor="hospital-name" className="block text-xs font-semibold text-slate-700">Preferred Hospital (optional)</label>
              <input id="hospital-name" className={inputClass} placeholder="e.g. Services Hospital" value={safetyProfile.preferred_hospital_name} onChange={(e) => setSafetyProfile({ ...safetyProfile, preferred_hospital_name: e.target.value })} />
            </div>
            <div>
              <label htmlFor="hospital-phone" className="block text-xs font-semibold text-slate-700">Hospital Phone (optional)</label>
              <input id="hospital-phone" className={inputClass} placeholder="e.g. 042-99203402" value={safetyProfile.preferred_hospital_phone} onChange={(e) => setSafetyProfile({ ...safetyProfile, preferred_hospital_phone: e.target.value })} />
            </div>
          </div>
          <label className="flex items-start gap-3 text-xs text-slate-800 cursor-pointer">
            <input type="checkbox" checked={safetyProfile.emergency_actions_consent} onChange={(e) => setSafetyProfile({ ...safetyProfile, emergency_actions_consent: e.target.checked })} className="mt-0.5 size-4 accent-indigo-600 rounded cursor-pointer" />
            <span><strong className="font-semibold text-slate-900">Show my saved emergency actions during a crisis</strong><br /><span className="text-slate-600 font-normal">This only enables call and SMS buttons that you press yourself. It does not grant MindGuard permission to dispatch services or send messages for you.</span></span>
          </label>
        </div>

        {/* Designated Emergency Trusted Contact */}
        <div className="space-y-3 rounded-2xl border border-slate-200/90 bg-white p-5 shadow-2xs">
          <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
            <Phone className="size-4 text-emerald-600" />
            <h2 className="text-sm font-bold text-slate-900 font-heading">Designated Emergency Trusted Contact</h2>
          </div>

          {/* Mandatory Safety Statement */}
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-relaxed text-amber-950 font-medium">
            <p className="font-semibold text-amber-900">Important Safety Notice:</p>
            <p>MindGuard never contacts this person automatically. Any call or message requires your explicit action.</p>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label htmlFor="contact-name" className="block text-xs font-semibold text-slate-700">Contact Name</label>
              <input
                id="contact-name"
                className={inputClass}
                placeholder="e.g. Sara Ahmed"
                value={contact.name}
                onChange={(e) => setContact({ ...contact, name: e.target.value })}
              />
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label htmlFor="contact-phone" className="block text-xs font-semibold text-slate-700">Phone Number</label>
                {contact.phone && (
                  <button
                    type="button"
                    onClick={() => setMaskPhone(!maskPhone)}
                    className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-600 hover:text-indigo-800 cursor-pointer"
                  >
                    {maskPhone ? <Eye className="size-3" /> : <EyeOff className="size-3" />}
                    <span>{maskPhone ? "Show" : "Mask"}</span>
                  </button>
                )}
              </div>
              <input
                id="contact-phone"
                className={inputClass}
                placeholder="e.g. +92 300 1234567"
                type={maskPhone && contact.phone ? "password" : "text"}
                value={contact.phone}
                onChange={(e) => setContact({ ...contact, phone: e.target.value })}
              />
              {contact.phone && maskPhone && (
                <p className="text-[11px] text-slate-500 mt-1">
                  Masked preview: {maskPhoneNumber(contact.phone)}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="contact-rel" className="block text-xs font-semibold text-slate-700">Relationship</label>
              <input
                id="contact-rel"
                className={inputClass}
                placeholder="e.g. Friend or family"
                value={contact.relationship || ""}
                onChange={(e) => setContact({ ...contact, relationship: e.target.value })}
              />
            </div>
          </div>
        </div>

        {/* Save Settings Primary Button */}
        <div>
          <button
            type="button"
            disabled={isSaving}
            onClick={save}
            className="rounded-xl bg-indigo-600 px-5 py-2.5 text-xs font-semibold text-white shadow-2xs transition-colors hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-50 cursor-pointer"
          >
            {isSaving ? "Saving Settings..." : "Save Settings & Preferences"}
          </button>
        </div>

        {/* Data Export & Account Actions */}
        <div className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-2xs space-y-4">
          <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
            <Database className="size-4 text-slate-700" />
            <h2 className="text-sm font-bold text-slate-900 font-heading">Data Management &amp; Account Rights</h2>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-bold text-slate-900">Export Machine-Readable Personal Data</p>
              <p className="text-xs text-slate-600">Download a full JSON copy of your chat history, sessions, and mood entries.</p>
            </div>
            <button
              type="button"
              onClick={downloadExport}
              className="flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-800 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 cursor-pointer shadow-2xs"
            >
              <Download className="size-4 text-indigo-600" />
              <span>Export JSON</span>
            </button>
          </div>

          <div className="border-t border-rose-100 pt-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-bold text-rose-900 flex items-center gap-1.5">
                <AlertOctagon className="size-4 text-rose-600" /> Permanent Account Deletion
              </p>
              <p className="text-xs text-slate-600">Permanently purge your profile, credentials, and all recorded data from the database.</p>
            </div>
            <button
              type="button"
              onClick={() => {
                setDeleteConfirmText("");
                setShowDeleteModal(true);
              }}
              className="flex items-center gap-2 rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-rose-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400 cursor-pointer shadow-2xs"
            >
              <Trash2 className="size-4" />
              <span>Delete Account</span>
            </button>
          </div>
        </div>

        {/* Deliberate Two-Step Account Deletion Confirmation Modal */}
        {showDeleteModal && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-account-title"
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-xs"
          >
            <div className="w-full max-w-md rounded-2xl border border-rose-300 bg-white p-6 shadow-2xl space-y-4">
              <div className="flex items-center gap-3 text-rose-700">
                <AlertOctagon className="size-6 shrink-0" />
                <h3 id="delete-account-title" className="text-base font-bold text-slate-900 font-heading">
                  Confirm Account &amp; Data Deletion
                </h3>
              </div>
              <p className="text-xs text-slate-700 leading-relaxed">
                This is a permanent, destructive action. All stored chat history, mood logs, and account records will be permanently removed.
              </p>
              <div>
                <label htmlFor="delete-confirm-input" className="block text-xs font-semibold text-slate-800 mb-1">
                  To confirm, type <span className="font-mono font-bold text-rose-700">DELETE</span> below:
                </label>
                <input
                  id="delete-confirm-input"
                  type="text"
                  placeholder="DELETE"
                  value={deleteConfirmText}
                  onChange={(e) => setDeleteConfirmText(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-xs text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 font-mono"
                />
              </div>
              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowDeleteModal(false)}
                  className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={deleteConfirmText.trim().toUpperCase() !== "DELETE" || isDeleting}
                  onClick={executeAccountDeletion}
                  className="rounded-xl bg-rose-600 px-4 py-2 text-xs font-bold text-white transition-colors hover:bg-rose-700 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                >
                  {isDeleting ? "Deleting..." : "Permanently Delete"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
