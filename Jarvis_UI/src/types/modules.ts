export type ModuleId = 'MEMORY' | 'SKILLS' | 'CHARACTER' | 'SETTINGS';
export type CharacterAppearance = 'male' | 'female';

export interface ModuleConnector {
  id: ModuleId;
  label: string;
  color: 'cyan' | 'green' | 'red' | 'blue';
  icon: string;
  status: 'connected' | 'degraded' | 'unavailable' | 'syncing';
  statusLabel: string;
  itemCount?: number;
  details: string;
}

export interface MemoryRecord {
  id: string;
  category: 'preference' | 'fact' | 'credential' | 'workflow';
  key: string;
  value: string;
  updatedAt: string;
  source: string;
}

export interface SkillRecord {
  id: string;
  name: string;
  description: string;
  category: string;
  status: 'active' | 'standby' | 'error';
  version: string;
  author: string;
}

export interface CharacterPersona {
  appearance: CharacterAppearance;
  name: string;
  role: string;
  tone: 'Professional & Sci-Fi' | 'Concise & Technical' | 'Warm & Conversational';
  voiceId: string;
  speed: number;
  pitch: number;
  personalityTraits: string[];
}
