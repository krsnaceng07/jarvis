export type AssistantState =
  | 'idle'
  | 'listening'
  | 'transcribing'
  | 'thinking'
  | 'speaking'
  | 'tool_running'
  | 'waiting_for_permission'
  | 'cancelling'
  | 'cancelled'
  | 'disconnected'
  | 'error';

export type AssistantMode = 'new' | 'classic';

export interface AssistantStatusInfo {
  state: AssistantState;
  displayText: string;
  isListening: boolean;
  canCancel: boolean;
  awarenessEnabled: boolean;
  mode: AssistantMode;
  systemName: string;
  version: string;
}
