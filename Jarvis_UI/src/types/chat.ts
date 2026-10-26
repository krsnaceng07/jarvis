export type RightPanelTab = 'VOICE' | 'AGENT' | 'NOTES';

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant' | 'system';
  text: string;
  timestamp: string;
  status: 'sending' | 'sent' | 'streaming' | 'completed' | 'error';
  audioUrl?: string;
  suggestedActions?: string[];
  toolCalls?: Array<{
    toolName: string;
    params: Record<string, unknown>;
    result?: string;
    status: 'running' | 'completed' | 'error';
  }>;
}

export interface AgentTask {
  id: string;
  title: string;
  status: 'queued' | 'running' | 'waiting_for_approval' | 'completed' | 'failed' | 'cancelled';
  currentStep: string;
  progress: number | null;
  startedAt: string;
  durationMs?: number;
  toolsUsed: string[];
}

export interface NoteItem {
  id: string;
  title: string;
  content: string;
  updatedAt: string;
  tags: string[];
}
