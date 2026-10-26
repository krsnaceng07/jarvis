import { useState, useEffect } from 'react';
import { AssistantState, AssistantMode } from '../types/assistant';
import { audioService } from '../services/audioService';
import { backendBridge } from '../services/backendBridge';

interface AssistantStoreState {
  state: AssistantState;
  displayText: string;
  isListening: boolean;
  canCancel: boolean;
  awarenessEnabled: boolean;
  mode: AssistantMode;
  systemName: string;
  version: string;
}

const defaultState: AssistantStoreState = {
  state: 'listening',
  displayText: 'Jarvis is listening',
  isListening: true,
  canCancel: true,
  awarenessEnabled: true,
  mode: 'new',
  systemName: 'JARVIS',
  version: 'v3.1.17',
};

// Global observable state for React hooks
let currentStoreState = { ...defaultState };
const listeners = new Set<(state: AssistantStoreState) => void>();

function notify() {
  listeners.forEach(fn => fn({ ...currentStoreState }));
}

export const assistantStore = {
  getState(): AssistantStoreState {
    return { ...currentStoreState };
  },

  setState(newState: AssistantState, customText?: string) {
    const textMap: Record<AssistantState, string> = {
      idle: 'System Standby',
      listening: 'Jarvis is listening',
      transcribing: 'Processing speech input...',
      thinking: 'Analyzing context & synthesizing...',
      speaking: 'Responding via voice output...',
      tool_running: 'Executing autonomous tool...',
      waiting_for_permission: 'Awaiting human authorization...',
      cancelling: 'Aborting operation...',
      cancelled: 'Operation terminated',
      disconnected: 'Offline / Standalone mode',
      error: 'System error detected',
    };

    currentStoreState.state = newState;
    currentStoreState.displayText = customText || textMap[newState];
    currentStoreState.isListening = newState === 'listening';
    currentStoreState.canCancel = ['listening', 'thinking', 'speaking', 'tool_running'].includes(newState);
    notify();
  },

  toggleListening() {
    if (currentStoreState.isListening) {
      audioService.playMicPing(false);
      backendBridge.setMuted(true);
      this.setState('idle', 'Microphone muted');
    } else {
      audioService.playMicPing(true);
      backendBridge.setMuted(false);
      this.setState('listening', 'Jarvis is listening');
    }
  },

  terminate() {
    audioService.playTerminateAlarm();
    backendBridge.terminate();
    this.setState('cancelled', 'TERMINATED — All active tasks halted');
    setTimeout(() => {
      this.setState('idle', 'System Standby');
    }, 2800);
  },

  toggleAwareness() {
    audioService.playClick();
    currentStoreState.awarenessEnabled = !currentStoreState.awarenessEnabled;
    notify();
  },

  setMode(mode: AssistantMode) {
    audioService.playClick();
    currentStoreState.mode = mode;
    notify();
  },

  setSystemName(name: string) {
    currentStoreState.systemName = name;
    notify();
  }
};

export function useAssistant() {
  const [state, setState] = useState<AssistantStoreState>(assistantStore.getState());

  useEffect(() => {
    listeners.add(setState);
    return () => {
      listeners.delete(setState);
    };
  }, []);

  return {
    ...state,
    setAssistantState: (st: AssistantState, txt?: string) => assistantStore.setState(st, txt),
    toggleListening: () => assistantStore.toggleListening(),
    terminate: () => assistantStore.terminate(),
    toggleAwareness: () => assistantStore.toggleAwareness(),
    setMode: (m: AssistantMode) => assistantStore.setMode(m),
    setSystemName: (n: string) => assistantStore.setSystemName(n),
  };
}
