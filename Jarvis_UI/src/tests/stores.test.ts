import { describe, it, expect } from 'vitest';
import { chatStore } from '../state/chatStore';
import { moduleStore } from '../state/moduleStore';
import { visualHubStore } from '../state/visualHubStore';

describe('JARVIS Stores & Subsystems', () => {
  it('handles chat tab switching', () => {
    chatStore.setActiveTab('AGENT');
    expect(chatStore.getState().activeTab).toBe('AGENT');

    chatStore.setActiveTab('NOTES');
    expect(chatStore.getState().activeTab).toBe('NOTES');

    chatStore.setActiveTab('VOICE');
    expect(chatStore.getState().activeTab).toBe('VOICE');
  });

  it('adds and deletes notes correctly', () => {
    const initialCount = chatStore.getState().notes.length;
    chatStore.addNote('Test Memo', 'Content of test memo', ['Testing']);
    
    expect(chatStore.getState().notes.length).toBe(initialCount + 1);
    expect(chatStore.getState().notes[0].title).toBe('Test Memo');

    const createdId = chatStore.getState().notes[0].id;
    chatStore.deleteNote(createdId);
    expect(chatStore.getState().notes.length).toBe(initialCount);
  });

  it('manages modal open and close states', () => {
    moduleStore.openModal('MEMORY');
    expect(moduleStore.getState().activeModal).toBe('MEMORY');

    moduleStore.openModal('SKILLS');
    expect(moduleStore.getState().activeModal).toBe('SKILLS');

    moduleStore.closeModal();
    expect(moduleStore.getState().activeModal).toBeNull();
  });

  it('toggles skill standby and active states', () => {
    const skill = moduleStore.getState().skills[0];
    const initialStatus = skill.status;

    moduleStore.toggleSkill(skill.id);
    const updated = moduleStore.getState().skills.find(s => s.id === skill.id);
    expect(updated?.status).not.toBe(initialStatus);

    // Revert
    moduleStore.toggleSkill(skill.id);
    const reverted = moduleStore.getState().skills.find(s => s.id === skill.id);
    expect(reverted?.status).toBe(initialStatus);
  });

  it('updates visual hub prompt selection', () => {
    visualHubStore.selectPrompt('p-1');
    expect(visualHubStore.getState().selectedPromptId).toBe('p-1');
    expect(visualHubStore.getState().activeModelType).toBe('blueprint');

    visualHubStore.selectPrompt('p-2');
    expect(visualHubStore.getState().activeModelType).toBe('blackhole');
  });

  it('collapses progressive speech fragments into a single message bubble', () => {
    chatStore.clearChat();
    // Simulate speech partials: "ti" -> "Timi" -> "Timi ke" -> "Timi ke ke garna sakchhau?"
    chatStore.addMessage('user', 'ti');
    expect(chatStore.getState().messages.length).toBe(1);
    expect(chatStore.getState().messages[0].text).toBe('ti');

    chatStore.addMessage('user', 'Timi');
    expect(chatStore.getState().messages.length).toBe(1);
    expect(chatStore.getState().messages[0].text).toBe('Timi');

    chatStore.addMessage('user', 'Timi ke ke garna sakchhau?');
    expect(chatStore.getState().messages.length).toBe(1);
    expect(chatStore.getState().messages[0].text).toBe('Timi ke ke garna sakchhau?');
  });

  it('manages real-time live input and single-sentence turn commit', () => {
    chatStore.clearChat();
    chatStore.setLiveInput('Mero naam', false);
    expect(chatStore.getState().liveInputText).toBe('Mero naam');
    expect(chatStore.getState().isLiveTranscribing).toBe(true);
    // Messages array remains untouched while user is speaking
    expect(chatStore.getState().messages.length).toBe(0);

    chatStore.setLiveInput('Mero naam Jarvis ho ki haina?', false);
    expect(chatStore.getState().liveInputText).toBe('Mero naam Jarvis ho ki haina?');
    expect(chatStore.getState().messages.length).toBe(0);

    // Turn completes
    chatStore.commitLiveInput('Mero naam Jarvis ho ki haina?');
    expect(chatStore.getState().liveInputText).toBe('');
    expect(chatStore.getState().isLiveTranscribing).toBe(false);
    expect(chatStore.getState().messages.length).toBe(1);
    expect(chatStore.getState().messages[0].text).toBe('Mero naam Jarvis ho ki haina?');
  });
});
