import { useState, useEffect } from 'react';
import { ModuleId, ModuleConnector, MemoryRecord, SkillRecord, CharacterPersona } from '../types/modules';
import { audioService } from '../services/audioService';
import { backendBridge } from '../services/backendBridge';

interface ModuleStoreState {
  activeModal: ModuleId | null;
  modules: Record<ModuleId, ModuleConnector>;
  memories: MemoryRecord[];
  skills: SkillRecord[];
  character: CharacterPersona;
  settings: {
    theme: 'Dark Sci-Fi (Default)' | 'Cyberpunk' | 'Deep Space';
    speechRate: number;
    audioVolume: number;
    vadSensitivity: number;
    autoBargeIn: boolean;
    localServerPort: number;
  };
}

const defaultModules: Record<ModuleId, ModuleConnector> = {
  MEMORY: {
    id: 'MEMORY',
    label: 'MEMORY',
    color: 'cyan',
    icon: 'Brain',
    status: 'connected',
    statusLabel: 'ONLINE • FTS5 + LanceDB',
    itemCount: 1420,
    details: 'Dual persistence active. SQLite FTS5 index and LanceDB semantic vectors synced.'
  },
  SKILLS: {
    id: 'SKILLS',
    label: 'SKILLS',
    color: 'green',
    icon: 'BookOpen',
    status: 'connected',
    statusLabel: '48 ACTIVE SKILLS',
    itemCount: 48,
    details: 'Declarative agent skills loaded with self-healing tool argument recovery.'
  },
  CHARACTER: {
    id: 'CHARACTER',
    label: 'CHARACTER',
    color: 'red',
    icon: 'Shield',
    status: 'connected',
    statusLabel: 'JARVIS PRIME',
    details: 'Autonomous AI Persona with high-reliability directive and proactive intuition.'
  },
  SETTINGS: {
    id: 'SETTINGS',
    label: 'SETTINGS',
    color: 'blue',
    icon: 'Settings',
    status: 'connected',
    statusLabel: 'SYSTEM OPTIMAL',
    details: 'Gateway listening on 127.0.0.1:7433. Audio 16kHz PCM duplex loop enabled.'
  }
};

const defaultMemories: MemoryRecord[] = [
  { id: 'mem-1', category: 'fact', key: 'user_preferred_name', value: 'Krishna / Sir', updatedAt: '2026-10-24', source: 'USER.md' },
  { id: 'mem-2', category: 'preference', key: 'channel_fav_editor', value: 'Neovim via Telegram', updatedAt: '2026-10-24', source: 'Telegram Bridge' },
  { id: 'mem-3', category: 'fact', key: 'location', value: 'Sinamangal, Kathmandu (UTC+5:45)', updatedAt: '2026-10-24', source: 'Core State' },
  { id: 'mem-4', category: 'workflow', key: 'audio_barge_in_latency', value: '<40ms preemption buffer', updatedAt: '2026-10-23', source: 'Desktop Host' },
  { id: 'mem-5', category: 'workflow', key: 'vector_db_path', value: '~/.jarvis/state/lance/embeddings', updatedAt: '2026-10-22', source: 'LanceDB' },
];

const defaultSkills: SkillRecord[] = [
  { id: 'sk-1', name: 'cua-computer', category: 'Automation', description: 'Native OS Automation, keyboard/mouse controller, window bounding boxes.', status: 'active', version: '2.4.0', author: 'OpenClaw' },
  { id: 'sk-2', name: 'browser-control', category: 'Web', description: 'Playwright/Selenium browser runtime with DOM SOM element grounding.', status: 'active', version: '1.9.2', author: 'JARVIS Core' },
  { id: 'sk-3', name: 'silero-vad', category: 'Audio', description: 'Neural voice activity detection ONNX model running at 32ms cadence.', status: 'active', version: '3.1.0', author: 'Audio Core' },
  { id: 'sk-4', name: 'sqlite-fts5-search', category: 'Memory', description: 'Full-text indexed associative memory retrieval and auto-scrubbing.', status: 'active', version: '2.0.1', author: 'Memory SDK' },
  { id: 'sk-5', name: 'subagent-orchestrator', category: 'Multi-Agent', description: 'Autonomous parallel lane spawner with terminal outcome aggregation.', status: 'active', version: '1.5.0', author: 'Agent Runtime' },
  { id: 'sk-6', name: 'ui-ux-pro-max', category: 'Design', description: 'WCAG AAA design intelligence, token harmonics, and HUD styling.', status: 'active', version: '4.0.0', author: 'Design Suite' }
];

const defaultCharacter: CharacterPersona = {
  appearance: 'male',
  name: 'JARVIS',
  role: 'Autonomous Multimodal Executive AI',
  tone: 'Professional & Sci-Fi',
  voiceId: 'British English / Natural Neural',
  speed: 1.05,
  pitch: 0.95,
  personalityTraits: ['Analytical', 'Proactive', 'Loyal', 'Deterministic', 'Uncompromising Reliability']
};

// Character choice is user state, not a cache: it must survive a reload so the
// dashboard and the onboarding view stop disagreeing after a restart.
const CHARACTER_STORAGE_KEY = 'jarvis.character.v1';

function loadStoredCharacter(): CharacterPersona {
  if (typeof window === 'undefined') return defaultCharacter;
  try {
    const raw = window.localStorage.getItem(CHARACTER_STORAGE_KEY);
    if (!raw) return defaultCharacter;
    const parsed = JSON.parse(raw) as Partial<CharacterPersona>;
    return {
      ...defaultCharacter,
      ...parsed,
      appearance: parsed.appearance === 'female' ? 'female' : 'male',
      personalityTraits:
        Array.isArray(parsed.personalityTraits) && parsed.personalityTraits.length > 0
          ? parsed.personalityTraits.filter((trait): trait is string => typeof trait === 'string')
          : defaultCharacter.personalityTraits,
    };
  } catch {
    return defaultCharacter;
  }
}

function persistCharacter(character: CharacterPersona): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(CHARACTER_STORAGE_KEY, JSON.stringify(character));
  } catch {
    // Storage can be unavailable in hardened webviews; the live state still works.
  }
}

let moduleStoreState: ModuleStoreState = {
  activeModal: null,
  modules: defaultModules,
  memories: defaultMemories,
  skills: defaultSkills,
  character: loadStoredCharacter(),
  settings: {
    theme: 'Dark Sci-Fi (Default)',
    speechRate: 1.05,
    audioVolume: 90,
    vadSensitivity: 0.55,
    autoBargeIn: true,
    localServerPort: 7433
  }
};

const listeners = new Set<(state: ModuleStoreState) => void>();

function notify() {
  listeners.forEach(fn => fn({ ...moduleStoreState }));
}

export const moduleStore = {
  getState(): ModuleStoreState {
    return { ...moduleStoreState };
  },

  openModal(id: ModuleId) {
    audioService.playActivate();
    moduleStoreState.activeModal = id;
    notify();
  },

  closeModal() {
    audioService.playClick();
    moduleStoreState.activeModal = null;
    notify();
  },

  async syncWithBackend() {
    try {
      const [backendMems, backendSkills] = await Promise.all([
        backendBridge.fetchMemories(),
        backendBridge.fetchSkills(),
      ]);

      if (backendMems && backendMems.length > 0) {
        moduleStoreState.memories = backendMems;
        moduleStoreState.modules.MEMORY.itemCount = backendMems.length;
        moduleStoreState.modules.MEMORY.statusLabel = `${backendMems.length} MEMORIES ACTIVE`;
      }

      if (backendSkills && backendSkills.length > 0) {
        moduleStoreState.skills = backendSkills;
        moduleStoreState.modules.SKILLS.itemCount = backendSkills.length;
        moduleStoreState.modules.SKILLS.statusLabel = `${backendSkills.length} SKILLS LOADED`;
      }
      notify();
    } catch (e) {
      console.warn('[ModuleStore] Sync error:', e);
    }
  },

  addMemory(key: string, value: string, category: 'preference' | 'fact' | 'credential' | 'workflow') {
    audioService.playActivate();
    const newRecord: MemoryRecord = {
      id: `mem-${Date.now()}`,
      category,
      key,
      value,
      updatedAt: 'Just now',
      source: 'User Input'
    };
    moduleStoreState.memories = [newRecord, ...moduleStoreState.memories];
    moduleStoreState.modules.MEMORY.itemCount = moduleStoreState.memories.length;
    notify();
    backendBridge.addMemory(key, value, category);
  },

  deleteMemory(id: string) {
    audioService.playClick();
    moduleStoreState.memories = moduleStoreState.memories.filter(m => m.id !== id);
    moduleStoreState.modules.MEMORY.itemCount = moduleStoreState.memories.length;
    notify();
    backendBridge.deleteMemory(id);
  },

  toggleSkill(id: string) {
    audioService.playClick();
    moduleStoreState.skills = moduleStoreState.skills.map(s => {
      if (s.id === id) {
        const nextStatus = s.status === 'active' ? 'standby' : 'active';
        return { ...s, status: nextStatus };
      }
      return s;
    });
    notify();
  },

  updateCharacter(updates: Partial<CharacterPersona>) {
    audioService.playActivate();
    moduleStoreState.character = { ...moduleStoreState.character, ...updates };
    persistCharacter(moduleStoreState.character);
    notify();
  },

  updateSettings(updates: Partial<ModuleStoreState['settings']>) {
    audioService.playClick();
    moduleStoreState.settings = { ...moduleStoreState.settings, ...updates };
    notify();
  }
};

export function useModules() {
  const [state, setState] = useState<ModuleStoreState>(moduleStore.getState());

  useEffect(() => {
    listeners.add(setState);
    moduleStore.syncWithBackend();
    return () => {
      listeners.delete(setState);
    };
  }, []);

  return {
    ...state,
    syncWithBackend: () => moduleStore.syncWithBackend(),
    openModal: (id: ModuleId) => moduleStore.openModal(id),
    closeModal: () => moduleStore.closeModal(),
    addMemory: (k: string, v: string, cat: 'preference' | 'fact' | 'credential' | 'workflow') => moduleStore.addMemory(k, v, cat),
    deleteMemory: (id: string) => moduleStore.deleteMemory(id),
    toggleSkill: (id: string) => moduleStore.toggleSkill(id),
    updateCharacter: (up: Partial<CharacterPersona>) => moduleStore.updateCharacter(up),
    updateSettings: (up: Partial<ModuleStoreState['settings']>) => moduleStore.updateSettings(up),
  };
}
