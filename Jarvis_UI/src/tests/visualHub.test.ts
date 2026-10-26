import { describe, it, expect } from 'vitest';
import { visualHubStore } from '../state/visualHubStore';

describe('Visual Hub Subsystem', () => {
  it('switches between visual hub and gesture tabs', () => {
    visualHubStore.setActiveTab('gesture');
    expect(visualHubStore.getState().activeTab).toBe('gesture');

    visualHubStore.setActiveTab('visual hub');
    expect(visualHubStore.getState().activeTab).toBe('visual hub');
  });

  it('cycles through all 4 3D prompt models accurately', () => {
    // 01 Starship
    visualHubStore.selectPrompt('p-1');
    expect(visualHubStore.getState().activeModelType).toBe('blueprint');

    // 02 Black Hole
    visualHubStore.selectPrompt('p-2');
    expect(visualHubStore.getState().activeModelType).toBe('blackhole');

    // 03 Fusion Reactor
    visualHubStore.selectPrompt('p-3');
    expect(visualHubStore.getState().activeModelType).toBe('fusion');

    // 04 Mars Mission
    visualHubStore.selectPrompt('p-4');
    expect(visualHubStore.getState().activeModelType).toBe('mars');
  });

  it('toggles fullscreen expanded view', () => {
    const initial = visualHubStore.getState().isExpanded;
    visualHubStore.toggleExpanded();
    expect(visualHubStore.getState().isExpanded).toBe(!initial);
    visualHubStore.toggleExpanded();
    expect(visualHubStore.getState().isExpanded).toBe(initial);
  });

  it('adds and retains items in the library history strip', () => {
    const initialCount = visualHubStore.getState().historyItems.length;
    visualHubStore.addHistoryItem({
      id: `h-test-${Date.now()}`,
      title: 'Quantum Telemetry Map',
      date: 'Oct 24',
      thumbnailType: 'diagram',
      category: 'Quantum',
    });
    expect(visualHubStore.getState().historyItems.length).toBe(initialCount + 1);
  });
});
