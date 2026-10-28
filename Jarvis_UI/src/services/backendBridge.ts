/**
 * JARVIS Full-Duplex Backend WebSocket & REST Bridge Client.
 * Connects the React + TypeScript frontend to the Python agent engine.
 */

import { assistantStore } from '../state/assistantStore';
import { chatStore } from '../state/chatStore';
import type { AssistantState } from '../types/assistant';

export interface SystemStatus {
  status: string;
  state: string;
  muted: boolean;
  model: string;
  engine: string;
  cpu_percent?: number;
  memory_percent?: number;
}

export interface BackendModuleData {
  MEMORY: { statusLabel: string; sqlite_canonical: boolean; vector_index: string };
  SKILLS: { statusLabel: string; tools_count: number; active: boolean };
  CHARACTER: { statusLabel: string; particles: number; mode: string };
  SETTINGS: { statusLabel: string; vad_engine: string; audio_rate: string };
}

type ConnectionListener = (connected: boolean) => void;
type AudioLevelListener = (level: number) => void;

class BackendBridgeService {
  private ws: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private isExplicitlyClosed = false;
  private pendingMuted: boolean | null = null;
  private listeners = new Set<ConnectionListener>();
  private audioListeners = new Set<AudioLevelListener>();

  public isConnected = false;

  constructor() {
    if (typeof window !== 'undefined') {
      this.connect();
    }
  }

  public getWsUrl(): string {
    const loc = window.location;
    // Normalize localhost / 127.0.0.1 development ports to python backend on 7433
    const isDev = loc.port === '5173' || loc.hostname === 'localhost' || loc.hostname === '127.0.0.1';
    if (isDev && loc.port !== '7433') {
      return 'ws://127.0.0.1:7433/ws/ui';
    }
    const protocol = loc.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${loc.host}/ws/ui`;
  }

  public getHttpUrl(path: string): string {
    const loc = window.location;
    const isDev = loc.port === '5173' || loc.hostname === 'localhost' || loc.hostname === '127.0.0.1';
    if (isDev && loc.port !== '7433') {
      return `http://127.0.0.1:7433${path}`;
    }
    return `${loc.protocol}//${loc.host}${path}`;
  }

  public connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.isExplicitlyClosed = false;
    const url = this.getWsUrl();

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.notifyConnection(true);
        if (this.pendingMuted !== null) {
          this.sendMuted(this.pendingMuted);
          this.pendingMuted = null;
        }
        console.log('[JARVIS Bridge] Connected to Python Agent Engine at', url);
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.handleServerMessage(data);
        } catch (err) {
          console.warn('[JARVIS Bridge] Failed to parse frame:', err);
        }
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.notifyConnection(false);
        if (!this.isExplicitlyClosed) {
          this.scheduleReconnect();
        }
      };

      this.ws.onerror = (err) => {
        console.warn('[JARVIS Bridge] WebSocket error:', err);
      };
    } catch (e) {
      this.isConnected = false;
      this.notifyConnection(false);
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, 2500);
  }

  private notifyConnection(status: boolean): void {
    this.listeners.forEach((fn) => fn(status));
    if (!status) {
      assistantStore.setState('disconnected', 'Disconnected from Agent Engine');
    }
  }

  public onConnectionChange(fn: ConnectionListener): () => void {
    this.listeners.add(fn);
    fn(this.isConnected);
    return () => this.listeners.delete(fn);
  }

  public onAudioLevel(fn: AudioLevelListener): () => void {
    this.audioListeners.add(fn);
    return () => this.audioListeners.delete(fn);
  }

  private handleServerMessage(data: Record<string, any>): void {
    const { type } = data;

    switch (type) {
      case 'init': {
        if (typeof data.muted === 'boolean') {
          assistantStore.setMuted(data.muted);
        }
        const rawState = data.state || 'STANDBY';
        const mapped = this.mapBackendState(rawState);
        assistantStore.setState(mapped);

        // Hydrate structured chat messages on initial connection
        if (Array.isArray(data.recent_messages)) {
          for (const msg of data.recent_messages) {
            if (msg.sender && msg.text) {
              chatStore.addMessage(msg.sender, msg.text);
            }
          }
        } else if (Array.isArray(data.recent_logs)) {
          for (const item of data.recent_logs) {
            const text = item.text || '';
            if (text.startsWith('You:') || text.startsWith('User:')) {
              chatStore.addMessage('user', text.replace(/^(You|User):\s*/i, '').trim());
            } else if (text.startsWith('JARVIS:') || text.startsWith('Jarvis:')) {
              chatStore.addMessage('assistant', text.replace(/^(JARVIS|Jarvis):\s*/i, '').trim());
            }
          }
        }
        break;
      }

      case 'state': {
        const rawState = data.state || 'STANDBY';
        const mapped = this.mapBackendState(rawState);
        assistantStore.setState(mapped);
        break;
      }

      case 'transcript': {
        const rawText = data.text || '';
        const isFinal = Boolean(data.is_final);
        const role = data.role || (rawText.startsWith('JARVIS:') || rawText.startsWith('Jarvis:') ? 'assistant' : 'user');
        const cleanText = data.clean_text || rawText.replace(/^(You|User|JARVIS|Jarvis):\s*/i, '').trim();

        if (role === 'user') {
          if (!isFinal && cleanText) {
            // Live voice dictation: User is speaking!
            // Type directly into the MessageComposer input box in real time
            assistantStore.setState('transcribing', cleanText);
            chatStore.setLiveInput(cleanText, false);
          } else if (cleanText) {
            // Final complete utterance: User finished speaking!
            // Commit as ONE single line in the chat transcript and clear input
            assistantStore.setState('thinking', 'Formulating response...');
            chatStore.commitLiveInput(cleanText);
          } else if (isFinal && !cleanText) {
            // Turn completed or cleared
            chatStore.clearLiveInput();
          }
        } else if (role === 'assistant') {
          // If user had pending live input that wasn't finalized yet, commit it now before assistant speaks
          if (chatStore.getState().liveInputText) {
            chatStore.commitLiveInput();
          }
          if (cleanText) {
            assistantStore.setState('speaking', cleanText);
            chatStore.addMessage('assistant', cleanText);
          }
        } else {
          assistantStore.setState('speaking', rawText);
        }
        break;
      }

      case 'audio_level': {
        const level = typeof data.level === 'number' ? data.level : 0;
        this.audioListeners.forEach((fn) => fn(level));
        break;
      }

      case 'log': {
        const logText = data.text || '';
        // Note: Voice transcripts and chat messages are authoritatively handled by case 'transcript'.
        // Only fallback to log for user/assistant messages if not already recorded in chatStore.
        if (logText.startsWith('You:') || logText.startsWith('User:')) {
          const userMsg = logText.replace(/^(You|User):\s*/i, '').trim();
          const current = chatStore.getState();
          const exists = current.messages.some(
            (m) => m.sender === 'user' && m.text.toLowerCase() === userMsg.toLowerCase()
          );
          if (!exists && userMsg) {
            chatStore.addMessage('user', userMsg);
          }
        } else if (logText.startsWith('Jarvis:') || logText.startsWith('JARVIS:')) {
          const botMsg = logText.replace(/^(Jarvis|JARVIS):\s*/i, '').trim();
          const current = chatStore.getState();
          const exists = current.messages.some(
            (m) => m.sender === 'assistant' && m.text.toLowerCase() === botMsg.toLowerCase()
          );
          if (!exists && botMsg) {
            chatStore.addMessage('assistant', botMsg);
          }
        }
        break;
      }

      case 'muted': {
        if (typeof data.muted === 'boolean') {
          assistantStore.setMuted(data.muted);
        }
        break;
      }
    }
  }

  private mapBackendState(backendState: string): AssistantState {
    switch (backendState.toUpperCase()) {
      case 'STANDBY':
      case 'IDLE':
        return 'idle';
      case 'LISTENING':
        return 'listening';
      case 'HEARING':
        return 'transcribing';
      case 'THINKING':
        return 'thinking';
      case 'SPEAKING':
        return 'speaking';
      case 'INITIALISING':
      case 'INITIALIZING':
        return 'idle';
      default:
        return 'listening';
    }
  }

  public sendChatMessage(text: string): void {
    if (!text.trim()) return;

    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        action: 'chat_message',
        text: text.trim(),
      }));
    } else {
      // Fallback to REST API
      fetch(this.getHttpUrl('/api/chat'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text.trim() }),
      }).catch((err) => console.error('[JARVIS Bridge] REST fallback error:', err));
    }
  }

  public setMuted(muted: boolean): void {
    this.pendingMuted = muted;
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.sendMuted(muted);
      this.pendingMuted = null;
    }
  }

  private sendMuted(muted: boolean): void {
    this.ws?.send(JSON.stringify({ action: 'set_muted', muted }));
  }

  public terminate(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: 'terminate' }));
    }
  }

  public async fetchChatHistory(): Promise<void> {
    try {
      const res = await fetch(this.getHttpUrl('/api/chat/history'));
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.messages)) {
          for (const msg of data.messages) {
            if (msg.sender && msg.text) {
              chatStore.addMessage(msg.sender, msg.text);
            }
          }
        }
      }
    } catch {
      // silent fallback
    }
  }

  public async fetchStatus(): Promise<SystemStatus | null> {
    try {
      const res = await fetch(this.getHttpUrl('/api/status'));
      if (res.ok) {
        return (await res.json()) as SystemStatus;
      }
    } catch {
      // silent fallback
    }
    return null;
  }

  public async fetchModules(): Promise<BackendModuleData | null> {
    try {
      const res = await fetch(this.getHttpUrl('/api/modules'));
      if (res.ok) {
        return (await res.json()) as BackendModuleData;
      }
    } catch {
      // silent fallback
    }
    return null;
  }

  public async fetchMemories(): Promise<any[]> {
    try {
      const res = await fetch(this.getHttpUrl('/api/memories'));
      if (res.ok) {
        const data = await res.json();
        return data.memories || [];
      }
    } catch {
      // silent fallback
    }
    return [];
  }

  public async addMemory(key: string, value: string, category: string): Promise<boolean> {
    try {
      const res = await fetch(this.getHttpUrl('/api/memories'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key, value, category }),
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  public async deleteMemory(id: string): Promise<boolean> {
    try {
      const res = await fetch(this.getHttpUrl(`/api/memories/${id}`), {
        method: 'DELETE',
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  public async fetchSkills(): Promise<any[]> {
    try {
      const res = await fetch(this.getHttpUrl('/api/skills'));
      if (res.ok) {
        const data = await res.json();
        return data.skills || [];
      }
    } catch {
      // silent fallback
    }
    return [];
  }

  public async fetchTasks(): Promise<any[]> {
    try {
      const res = await fetch(this.getHttpUrl('/api/tasks'));
      if (res.ok) {
        const data = await res.json();
        return data.tasks || [];
      }
    } catch {
      // silent fallback
    }
    return [];
  }

  public async cancelTask(taskId: string): Promise<boolean> {
    try {
      const res = await fetch(this.getHttpUrl('/api/tasks/cancel'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ taskId }),
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  public async fetchNotes(): Promise<any[]> {
    try {
      const res = await fetch(this.getHttpUrl('/api/notes'));
      if (res.ok) {
        const data = await res.json();
        return data.notes || [];
      }
    } catch {
      // silent fallback
    }
    return [];
  }

  public async saveNote(note: { id?: string; title: string; content: string; tags?: string[] }): Promise<boolean> {
    try {
      const res = await fetch(this.getHttpUrl('/api/notes'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(note),
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  public async deleteNote(id: string): Promise<boolean> {
    try {
      const res = await fetch(this.getHttpUrl(`/api/notes/${id}`), {
        method: 'DELETE',
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  public async fetchHeadlines(): Promise<any[]> {
    try {
      const res = await fetch(this.getHttpUrl('/api/headlines'));
      if (res.ok) {
        const data = await res.json();
        return data.headlines || [];
      }
    } catch {
      // silent fallback
    }
    return [];
  }

  public async fetchSettings(): Promise<any> {
    try {
      const res = await fetch(this.getHttpUrl('/api/settings'));
      if (res.ok) {
        return await res.json();
      }
    } catch {
      // silent fallback
    }
    return null;
  }

  public async uploadFile(file: File): Promise<{ success: boolean; filename?: string; error?: string }> {
    try {
      const base64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });

      const res = await fetch(this.getHttpUrl('/api/upload'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: file.name, data: base64 }),
      });

      if (res.ok) {
        return await res.json();
      }
      return { success: false, error: 'Upload failed' };
    } catch (e: any) {
      return { success: false, error: e?.message || 'Upload error' };
    }
  }
}

export const backendBridge = new BackendBridgeService();
