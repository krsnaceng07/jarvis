import { useState, useEffect } from 'react';
import { VisualHubTab, VisualPrompt, VisualHistoryItem } from '../types/visualHub';
import { audioService } from '../services/audioService';

interface VisualHubStoreState {
  activeTab: VisualHubTab;
  prompts: VisualPrompt[];
  selectedPromptId: string | null;
  activeModelType: 'architecture' | 'blueprint' | 'blackhole' | 'fusion' | 'mars';
  historyItems: VisualHistoryItem[];
  isExpanded: boolean;
  isGenerating: boolean;
}

const defaultPrompts: VisualPrompt[] = [
  {
    id: 'p-1',
    number: '01',
    title: 'Draw a SpaceX Starship blueprint',
    description: 'Generates detailed cross-section schematic with Raptor 3 methane/LOX propulsion, grid fins, and hot-staging ring.',
    tags: ['Engineering', 'Aerospace', 'SpaceX']
  },
  {
    id: 'p-2',
    number: '02',
    title: 'Show how a black hole bends light',
    description: 'Simulates relativistic ray-tracing and gravitational lensing around a spinning Kerr event horizon.',
    tags: ['Astrophysics', 'Relativity', 'Cosmology']
  },
  {
    id: 'p-3',
    number: '03',
    title: 'Look inside a fusion reactor',
    description: 'Renders magnetic confinement D-T plasma torus inside a D-shaped vacuum vessel with superconducting coils.',
    tags: ['Nuclear', 'Plasma', 'Clean Energy']
  },
  {
    id: 'p-4',
    number: '04',
    title: 'Plan a crewed mission to Mars',
    description: 'Calculates orbital mechanics, Hohmann transit window, payload delta-v budget, and surface habitation base layout.',
    tags: ['Mission Planning', 'Martian Colony', 'Orbital']
  }
];

const defaultHistory: VisualHistoryItem[] = [
  { id: 'h-1', title: 'Realistic Birthday ...', date: 'Oct 13', thumbnailType: 'concept', category: 'Creative' },
  { id: 'h-2', title: 'JARVIS UI Conce...', date: 'Oct 6', thumbnailType: 'blueprint', category: 'Interface' },
  { id: 'h-3', title: 'JARVIS UI Conce...', date: 'Oct 6', thumbnailType: 'diagram', category: 'Architecture' },
  { id: 'h-4', title: 'Moonlit Serenade', date: 'Oct 5', thumbnailType: 'audio', category: 'Synthesizer' },
  { id: 'h-5', title: 'The Anatomy ...', date: 'Sep 28', thumbnailType: 'anatomy', category: 'Biology' },
];

let storeState: VisualHubStoreState = {
  activeTab: 'visual hub',
  prompts: defaultPrompts,
  selectedPromptId: null,
  activeModelType: 'architecture',
  historyItems: defaultHistory,
  isExpanded: false,
  isGenerating: false,
};

const listeners = new Set<(state: VisualHubStoreState) => void>();

function notify() {
  listeners.forEach(fn => fn({ ...storeState }));
}

export const visualHubStore = {
  getState(): VisualHubStoreState {
    return { ...storeState };
  },

  setActiveTab(tab: VisualHubTab) {
    audioService.playClick();
    storeState.activeTab = tab;
    notify();
  },

  selectPrompt(id: string) {
    audioService.playActivate();
    storeState.selectedPromptId = id;
    storeState.isGenerating = true;

    // Change 3D visualization based on selected prompt
    if (id === 'p-1') storeState.activeModelType = 'blueprint';
    else if (id === 'p-2') storeState.activeModelType = 'blackhole';
    else if (id === 'p-3') storeState.activeModelType = 'fusion';
    else if (id === 'p-4') storeState.activeModelType = 'mars';
    else storeState.activeModelType = 'architecture';

    notify();

    setTimeout(() => {
      storeState.isGenerating = false;
      notify();
    }, 800);
  },

  toggleExpanded() {
    audioService.playClick();
    storeState.isExpanded = !storeState.isExpanded;
    notify();
  },

  addHistoryItem(item: VisualHistoryItem) {
    storeState.historyItems = [item, ...storeState.historyItems];
    notify();
  }
};

export function useVisualHub() {
  const [state, setState] = useState<VisualHubStoreState>(visualHubStore.getState());

  useEffect(() => {
    listeners.add(setState);
    return () => {
      listeners.delete(setState);
    };
  }, []);

  return {
    ...state,
    setActiveTab: (t: VisualHubTab) => visualHubStore.setActiveTab(t),
    selectPrompt: (id: string) => visualHubStore.selectPrompt(id),
    toggleExpanded: () => visualHubStore.toggleExpanded(),
    addHistoryItem: (item: VisualHistoryItem) => visualHubStore.addHistoryItem(item),
  };
}
