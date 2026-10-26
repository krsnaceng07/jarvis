import { useState, useEffect } from 'react';
import { RightPanelTab, ChatMessage, AgentTask, NoteItem } from '../types/chat';
import { audioService } from '../services/audioService';
import { assistantStore } from './assistantStore';
import { speechService } from '../services/speechService';
import { backendBridge } from '../services/backendBridge';

interface ChatStoreState {
  activeTab: RightPanelTab;
  messages: ChatMessage[];
  tasks: AgentTask[];
  notes: NoteItem[];
  isReplying: boolean;
  liveInputText: string;
  isLiveTranscribing: boolean;
}

const initialTasks: AgentTask[] = [
  {
    id: 'task-01',
    title: 'SAT-LINK Atmospheric telemetry sync',
    status: 'completed',
    currentStep: 'Satellite orbital positioning locked',
    progress: 100,
    startedAt: '10:42:15',
    durationMs: 340,
    toolsUsed: ['sat_link_client', 'geo_mesh']
  },
  {
    id: 'task-02',
    title: 'LanceDB Hybrid Memory Indexing',
    status: 'running',
    currentStep: 'Vector embedding cluster refinement',
    progress: 68,
    startedAt: '10:44:02',
    toolsUsed: ['sqlite_fts5', 'lancedb_vector']
  },
  {
    id: 'task-03',
    title: 'CUA Desktop Arbiter Grounding',
    status: 'queued',
    currentStep: 'Waiting for visual coordinate anchor',
    progress: null,
    startedAt: '10:44:30',
    toolsUsed: ['computer_tool', 'ui_grounding']
  }
];

const initialNotes: NoteItem[] = [
  {
    id: 'note-1',
    title: 'Project Nebula Architecture',
    content: 'Full-duplex bidirectional stream operating on 16kHz audio input, Silero VAD 32ms windowing, and 40ms barge-in preemption cutoff.',
    updatedAt: 'Today at 09:14',
    tags: ['Architecture', 'Audio', 'Low-Latency']
  },
  {
    id: 'note-2',
    title: 'Mission Mars Orbit Parameters',
    content: 'Trans-Mars Injection delta-v: 3.6 km/s. Aerocapture window: 45km altitude periapsis. Starship methane/LOX boiloff mitigation protocol.',
    updatedAt: 'Oct 22, 18:30',
    tags: ['SpaceX', 'Orbital', 'Mission']
  }
];

let chatStoreState: ChatStoreState = {
  activeTab: 'VOICE',
  messages: [],
  tasks: initialTasks,
  notes: initialNotes,
  isReplying: false,
  liveInputText: '',
  isLiveTranscribing: false,
};

let liveInputTimer: ReturnType<typeof setTimeout> | null = null;

const listeners = new Set<(state: ChatStoreState) => void>();

function notify() {
  listeners.forEach(fn => fn({ ...chatStoreState }));
}

export const chatStore = {
  getState(): ChatStoreState {
    return { ...chatStoreState };
  },

  setActiveTab(tab: RightPanelTab) {
    audioService.playClick();
    chatStoreState.activeTab = tab;
    notify();
  },

  setLiveInput(text: string, isFinal = false) {
    if (liveInputTimer) {
      clearTimeout(liveInputTimer);
      liveInputTimer = null;
    }
    chatStoreState.liveInputText = text;
    chatStoreState.isLiveTranscribing = !isFinal && Boolean(text.trim());
    notify();

    // Safety fallback: if user paused speaking for 4.5s without turn_complete, finalize single bubble
    if (!isFinal && text.trim()) {
      liveInputTimer = setTimeout(() => {
        if (chatStoreState.liveInputText) {
          chatStore.commitLiveInput();
        }
      }, 4500);
    }
  },

  clearLiveInput() {
    if (liveInputTimer) {
      clearTimeout(liveInputTimer);
      liveInputTimer = null;
    }
    chatStoreState.liveInputText = '';
    chatStoreState.isLiveTranscribing = false;
    notify();
  },

  commitLiveInput(finalText?: string) {
    if (liveInputTimer) {
      clearTimeout(liveInputTimer);
      liveInputTimer = null;
    }
    const textToCommit = (finalText !== undefined ? finalText : chatStoreState.liveInputText).trim();
    chatStoreState.liveInputText = '';
    chatStoreState.isLiveTranscribing = false;
    notify();

    if (textToCommit) {
      chatStore.addMessage('user', textToCommit);
    }
  },

  addMessage(sender: 'user' | 'assistant', text: string) {
    if (!text.trim()) return;
    const trimmed = text.trim();

    // Deduplicate against recent messages to prevent duplicate bubbles
    const recent = chatStoreState.messages.slice(-4);
    if (recent.some((m) => m.sender === sender && m.text.toLowerCase() === trimmed.toLowerCase())) {
      return;
    }

    // Merge progressive speech fragments into a single cohesive bubble
    const lastIdx = chatStoreState.messages.length - 1;
    if (lastIdx >= 0) {
      const lastMsg = chatStoreState.messages[lastIdx];
      if (lastMsg && lastMsg.sender === sender) {
        // If the new text is a superset of the existing bubble, update in place
        if (trimmed.toLowerCase().startsWith(lastMsg.text.toLowerCase())) {
          chatStoreState.messages[lastIdx] = {
            ...lastMsg,
            text: trimmed,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          };
          notify();
          return;
        }
        // If existing bubble is already a superset of the new fragment, do not overwrite or append
        if (lastMsg.text.toLowerCase().startsWith(trimmed.toLowerCase())) {
          return;
        }
      }
    }

    const msg: ChatMessage = {
      id: `msg-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
      sender,
      text: trimmed,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      status: 'completed',
    };
    chatStoreState.messages = [...chatStoreState.messages, msg];
    notify();
  },

  sendMessage(text: string) {
    if (!text.trim()) return;

    audioService.playClick();

    const userMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: 'user',
      text: text.trim(),
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      status: 'sent',
    };

    chatStoreState.messages = [...chatStoreState.messages, userMsg];
    chatStoreState.isReplying = true;
    notify();

    // Trigger HUD state: Thinking
    assistantStore.setState('thinking', 'Analyzing input & formulating strategy...');
    audioService.playEarconChime();

    // If connected to live Python backend, forward message directly
    if (backendBridge.isConnected) {
      backendBridge.sendChatMessage(text.trim());
      chatStoreState.isReplying = false;
      return;
    }

    // Standalone fallback when disconnected from backend
    setTimeout(() => {
      assistantStore.setState('speaking', 'Jarvis is responding...');
      
      const responses: Record<string, string> = {
        starship: "SpaceX Starship blueprint loaded into the Visual Hub. The Raptor 3 engines provide 280 tons of thrust with full flow staged combustion. Heat shield tiles have been aerodynamically verified for orbital reentry velocity.",
        blackhole: "Visualizing gravitational lensing around the Kerr black hole event horizon. Photon sphere orbit calculation confirms extreme spacetime curvature bending background starlight by 360 degrees.",
        fusion: "Tokamak magnetic confinement chamber initialized. Superconducting toroidal field coils are stabilizing deuterium-tritium plasma at 150 million Kelvin.",
        mars: "Crewed trajectory computed. Hohmann transfer orbit departure scheduled with 6-month transit window, aerocapture deceleration, and autonomous propellant production on the Martian surface.",
      };

      const lower = text.toLowerCase();
      let replyText = "Understood, Sir. I have processed your instruction and coordinated the subsystem telemetry. All parameters are within optimal operational bounds.";
      
      if (lower.includes('starship') || lower.includes('blueprint')) replyText = responses.starship;
      else if (lower.includes('black hole') || lower.includes('light')) replyText = responses.blackhole;
      else if (lower.includes('fusion') || lower.includes('reactor')) replyText = responses.fusion;
      else if (lower.includes('mars') || lower.includes('mission')) replyText = responses.mars;
      else if (lower.includes('hello') || lower.includes('hi') || lower.includes('namaste')) {
        replyText = "Namaste Sir. JARVIS holographic interface online. All satellite feeds, memory vectors, and autonomous agent tools are ready for your command.";
      }

      const botMsg: ChatMessage = {
        id: `msg-${Date.now() + 1}`,
        sender: 'assistant',
        text: replyText,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        status: 'completed',
      };

      chatStoreState.messages = [...chatStoreState.messages, botMsg];
      chatStoreState.isReplying = false;
      notify();

      // Read out response if audio is enabled
      speechService.speak(replyText, () => {
        assistantStore.setState('listening', 'Jarvis is listening');
      });
    }, 1200);
  },

  async syncTasksAndNotes() {
    try {
      const [backendTasks, backendNotes] = await Promise.all([
        backendBridge.fetchTasks(),
        backendBridge.fetchNotes(),
      ]);

      if (backendTasks && backendTasks.length > 0) {
        chatStoreState.tasks = backendTasks;
      }
      if (backendNotes && backendNotes.length > 0) {
        chatStoreState.notes = backendNotes;
      }
      notify();

      // Also hydrate chat history if available from backend
      await backendBridge.fetchChatHistory();
    } catch (e) {
      console.warn('[ChatStore] Sync error:', e);
    }
  },

  cancelTask(taskId: string) {
    audioService.playTerminateAlarm();
    chatStoreState.tasks = chatStoreState.tasks.map(t => 
      t.id === taskId ? { ...t, status: 'cancelled', currentStep: 'Task aborted by operator' } : t
    );
    notify();
    backendBridge.cancelTask(taskId);
  },

  addNote(title: string, content: string, tags: string[] = ['General']) {
    audioService.playActivate();
    const newNote: NoteItem = {
      id: `note-${Date.now()}`,
      title,
      content,
      updatedAt: 'Just now',
      tags
    };
    chatStoreState.notes = [newNote, ...chatStoreState.notes];
    notify();
    backendBridge.saveNote(newNote);
  },

  updateNote(id: string, title: string, content: string) {
    chatStoreState.notes = chatStoreState.notes.map(n => 
      n.id === id ? { ...n, title, content, updatedAt: 'Just now' } : n
    );
    notify();
    const updated = chatStoreState.notes.find(n => n.id === id);
    if (updated) {
      backendBridge.saveNote(updated);
    }
  },

  deleteNote(id: string) {
    audioService.playClick();
    chatStoreState.notes = chatStoreState.notes.filter(n => n.id !== id);
    notify();
    backendBridge.deleteNote(id);
  },

  clearChat() {
    audioService.playClick();
    chatStoreState.messages = [];
    notify();
  }
};

export function useChat() {
  const [state, setState] = useState<ChatStoreState>(chatStore.getState());

  useEffect(() => {
    listeners.add(setState);
    chatStore.syncTasksAndNotes();
    return () => {
      listeners.delete(setState);
    };
  }, []);

  return {
    ...state,
    syncTasksAndNotes: () => chatStore.syncTasksAndNotes(),
    setActiveTab: (t: RightPanelTab) => chatStore.setActiveTab(t),
    sendMessage: (txt: string) => chatStore.sendMessage(txt),
    addMessage: (sender: 'user' | 'assistant', text: string) => chatStore.addMessage(sender, text),
    setLiveInput: (txt: string, isFinal?: boolean) => chatStore.setLiveInput(txt, isFinal),
    commitLiveInput: (txt?: string) => chatStore.commitLiveInput(txt),
    clearLiveInput: () => chatStore.clearLiveInput(),
    cancelTask: (id: string) => chatStore.cancelTask(id),
    addNote: (title: string, content: string, tags?: string[]) => chatStore.addNote(title, content, tags),
    updateNote: (id: string, title: string, content: string) => chatStore.updateNote(id, title, content),
    deleteNote: (id: string) => chatStore.deleteNote(id),
    clearChat: () => chatStore.clearChat(),
  };
}
