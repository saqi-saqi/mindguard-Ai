export type Tab = "chat" | "analytics" | "settings" | "auth";

export interface TrustedContact {
  name: string;
  phone: string;
  relationship?: string;
}

export interface SafetyProfile {
  preferred_hospital_name: string;
  preferred_hospital_phone: string;
  city_or_district: string;
  emergency_actions_consent: boolean;
}

export interface MindUser {
  id?: string;
  name: string;
  email: string;
  trusted_contact?: TrustedContact;
  safety_profile?: SafetyProfile;
  settings?: UserSettings;
}

export interface UserSettings {
  consent_given: boolean;
  retention_enabled: boolean;
  retention_days: number;
  locale: string;
  show_tone_insights?: boolean;
}

export interface MoodLog {
  id?: string;
  score: number;
  tags: string[];
  notes: string;
  created_at?: string;
}

export interface ChatMessage {
  id: string;
  sender: "user" | "bot";
  text: string;
  timestamp: string;
  risk_level?: string;
  intent?: string;
  intent_confidence?: number;
  emotion?: string;
  sentiment?: string;
  grounding_exercise?: string;
  isError?: boolean;
}

export interface Helpline {
  name?: string;
  organization?: string;
  contact?: string;
  contact_info?: string;
  website?: string;
  description?: string;
  is_emergency_service?: boolean;
  verification_status?: string;
  region?: string;
}

export interface CrisisResources {
  pakistan?: Helpline[];
}
