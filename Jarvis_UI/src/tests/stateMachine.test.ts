import { describe, it, expect, beforeEach } from 'vitest';
import { assistantStore } from '../state/assistantStore';

describe('JARVIS Assistant State Machine', () => {
  beforeEach(() => {
    assistantStore.setState('idle');
  });

  it('initializes with expected default state', () => {
    const state = assistantStore.getState();
    expect(state.state).toBe('idle');
    expect(state.systemName).toBe('JARVIS');
    expect(state.version).toBe('v3.1.17');
  });

  it('transitions from idle to listening correctly', () => {
    assistantStore.setState('listening');
    const state = assistantStore.getState();
    expect(state.state).toBe('listening');
    expect(state.isListening).toBe(true);
    expect(state.canCancel).toBe(true);
    expect(state.displayText).toBe('Jarvis is listening');
  });

  it('transitions to thinking when processing', () => {
    assistantStore.setState('thinking');
    const state = assistantStore.getState();
    expect(state.state).toBe('thinking');
    expect(state.isListening).toBe(false);
    expect(state.canCancel).toBe(true);
  });

  it('transitions to speaking when generating audio output', () => {
    assistantStore.setState('speaking');
    const state = assistantStore.getState();
    expect(state.state).toBe('speaking');
    expect(state.canCancel).toBe(true);
  });

  it('terminates active session immediately when terminate is invoked', () => {
    assistantStore.setState('listening');
    assistantStore.terminate();
    const state = assistantStore.getState();
    expect(state.state).toBe('cancelled');
    expect(state.displayText).toContain('TERMINATED');
  });

  it('toggles awareness state', () => {
    const initial = assistantStore.getState().awarenessEnabled;
    assistantStore.toggleAwareness();
    expect(assistantStore.getState().awarenessEnabled).toBe(!initial);
  });

  it('supports mode switching between new and classic', () => {
    assistantStore.setMode('classic');
    expect(assistantStore.getState().mode).toBe('classic');
    assistantStore.setMode('new');
    expect(assistantStore.getState().mode).toBe('new');
  });
});
