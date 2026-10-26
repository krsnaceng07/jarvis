import { describe, it, expect, vi, beforeEach } from 'vitest';
import { backendBridge } from '../services/backendBridge';
import { assistantStore } from '../state/assistantStore';
import { chatStore } from '../state/chatStore';

describe('BackendBridgeService Integration Tests', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('maps backend states to assistant states accurately', () => {
    // @ts-expect-error accessing private method for unit testing
    expect(backendBridge.mapBackendState('STANDBY')).toBe('idle');
    // @ts-expect-error accessing private method for unit testing
    expect(backendBridge.mapBackendState('LISTENING')).toBe('listening');
    // @ts-expect-error accessing private method for unit testing
    expect(backendBridge.mapBackendState('HEARING')).toBe('transcribing');
    // @ts-expect-error accessing private method for unit testing
    expect(backendBridge.mapBackendState('THINKING')).toBe('thinking');
    // @ts-expect-error accessing private method for unit testing
    expect(backendBridge.mapBackendState('SPEAKING')).toBe('speaking');
    // @ts-expect-error accessing private method for unit testing
    expect(backendBridge.mapBackendState('UNKNOWN')).toBe('listening');
  });

  it('processes state events and updates assistantStore', () => {
    // @ts-expect-error accessing private method for unit testing
    backendBridge.handleServerMessage({
      type: 'state',
      state: 'SPEAKING',
    });

    expect(assistantStore.getState().state).toBe('speaking');
  });

  it('processes user and assistant transcripts into chat messages', () => {
    chatStore.clearChat();

    // 1. User starts speaking (interim)
    // @ts-expect-error accessing private method for unit testing
    backendBridge.handleServerMessage({
      type: 'transcript',
      text: 'You: Timi',
      clean_text: 'Timi',
      role: 'user',
      is_final: false,
    });
    // In progress: types into liveInputText, messages stays 0
    expect(chatStore.getState().liveInputText).toBe('Timi');
    expect(chatStore.getState().messages.length).toBe(0);

    // 2. User continues speaking (interim)
    // @ts-expect-error accessing private method for unit testing
    backendBridge.handleServerMessage({
      type: 'transcript',
      text: 'You: Timi ke ke',
      clean_text: 'Timi ke ke',
      role: 'user',
      is_final: false,
    });
    expect(chatStore.getState().liveInputText).toBe('Timi ke ke');
    expect(chatStore.getState().messages.length).toBe(0);

    // 3. User finishes turn (final)
    // @ts-expect-error accessing private method for unit testing
    backendBridge.handleServerMessage({
      type: 'transcript',
      text: 'User: Timi ke ke garna sakchhau?',
      clean_text: 'Timi ke ke garna sakchhau?',
      role: 'user',
      is_final: true,
    });
    // Now committed as 1 user message
    expect(chatStore.getState().liveInputText).toBe('');
    expect(chatStore.getState().messages.length).toBe(1);
    expect(chatStore.getState().messages[0].sender).toBe('user');
    expect(chatStore.getState().messages[0].text).toBe('Timi ke ke garna sakchhau?');

    // 4. JARVIS responds (assistant)
    // @ts-expect-error accessing private method for unit testing
    backendBridge.handleServerMessage({
      type: 'transcript',
      text: 'JARVIS: Ma tapaaeenko kaamaharoo ko lagi tayar chhu, Sir.',
      clean_text: 'Ma tapaaeenko kaamaharoo ko lagi tayar chhu, Sir.',
      role: 'assistant',
      is_final: true,
    });
    expect(chatStore.getState().messages.length).toBe(2);
    expect(chatStore.getState().messages[1].sender).toBe('assistant');
    expect(chatStore.getState().messages[1].text).toBe('Ma tapaaeenko kaamaharoo ko lagi tayar chhu, Sir.');
  });

  it('dispatches audio level events to listeners', () => {
    let receivedLevel = -1;
    const unsub = backendBridge.onAudioLevel((lvl) => {
      receivedLevel = lvl;
    });

    // @ts-expect-error accessing private method for unit testing
    backendBridge.handleServerMessage({
      type: 'audio_level',
      level: 0.72,
    });

    expect(receivedLevel).toBeCloseTo(0.72);
    unsub();
  });

  it('handles muted notifications', () => {
    // @ts-expect-error accessing private method for unit testing
    backendBridge.handleServerMessage({
      type: 'muted',
      muted: true,
    });

    expect(assistantStore.getState().state).toBe('idle');
    expect(assistantStore.getState().displayText).toBe('Microphone Muted');
  });
});
