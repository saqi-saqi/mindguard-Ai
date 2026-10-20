export type Tab = "chat" | "analytics" | "settings" | "auth" | "admin";

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
  role?: string;
  trusted_contact?: TrustedContact;
  safety_profile?: SafetyProfile;
  settings?: UserSettings;
}

export interface SafetyLogEntry {
  id: string;
  timestamp: string;
  session_id?: string | null;
  user_id?: string | null;
  is_guest?: boolean;
  tier: number;
  rule_or_model: string;
  category: string;
  confidence?: number | null;
  action_taken: string;
  message_excerpt: string;
  message_hash?: string;
  resolved: boolean;
  reviewed?: boolean;
  admin_note?: string;
  reviewed_at?: string | null;
  reviewed_by?: string | null;
}

export interface SafetyLogStats {
  total_flags: number;
  unresolved_count: number;
  resolved_count: number;
  last_7_days: {
    total: number;
    tier_1: number;
    tier_2: number;
    tier_3: number;
    by_tier?: Record<number, number>;
    by_category?: Record<string, number>;
  };
  last_30_days: {
    total: number;
    tier_1: number;
    tier_2: number;
    tier_3: number;
    by_tier?: Record<number, number>;
    by_category?: Record<string, number>;
  };
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

export interface ChatSession {
  id: string;
  title: string;
  created_at?: string;
  last_message_at?: string;
  risk_state?: string;
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
  emergency_resources?: Helpline[];
}
