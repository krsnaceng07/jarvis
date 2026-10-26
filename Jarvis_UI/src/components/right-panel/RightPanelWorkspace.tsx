import React from 'react';
import { Plus, History, Terminal, Maximize2, SplitSquareVertical } from 'lucide-react';
import { useChat } from '../../state/chatStore';
import { VoiceTab } from './VoiceTab';
import { AgentTab } from './AgentTab';
import { NotesTab } from './NotesTab';
import { MessageComposer } from './MessageComposer';
import { audioService } from '../../services/audioService';

export const RightPanelWorkspace: React.FC = () => {
  const { activeTab, setActiveTab, clearChat } = useChat();

  const tabs: Array<'VOICE' | 'AGENT' | 'NOTES'> = ['VOICE', 'AGENT', 'NOTES'];

  return (
    <aside className="hud-panel-frame flex h-full min-h-0 w-full flex-col overflow-hidden select-none">
      {/* 1. Header Tab Row & Tool Actions */}
      <div className="flex h-[42px] shrink-0 items-center justify-between border-b border-[#18343c] bg-[#050d13] px-3">
        {/* Left: Tab Switcher (VOICE, AGENT, NOTES) */}
        <div className="flex items-center">
          {tabs.map((tab, index) => {
            const isActive = activeTab === tab;
            return (
              <React.Fragment key={tab}>
                {index > 0 && <span className="mx-3 h-3 w-px bg-[#1e3a44]" aria-hidden="true" />}
                <button
                  onClick={() => setActiveTab(tab)}
                  className={`relative py-2 text-[11px] font-bold uppercase tracking-[0.16em] transition-colors ${
                    isActive
                      ? 'text-cyan-300'
                      : 'text-slate-500 hover:text-slate-200'
                  }`}
                >
                  <span>{tab}</span>
                </button>
              </React.Fragment>
            );
          })}
        </div>

        {/* Right: Utility Icons (+, history, terminal, expand, split) */}
        <div className="flex items-center space-x-1.5 text-slate-400">
          <button
            onClick={() => {
              audioService.playClick();
              clearChat();
            }}
            className="p-1 hover:text-cyan-300 transition-colors"
            title="Start New Session (+)"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => audioService.playClick()}
            className="p-1 hover:text-cyan-300 transition-colors"
            title="Session History"
          >
            <History className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => audioService.playClick()}
            className="p-1 hover:text-cyan-300 transition-colors"
            title="Terminal Command Mode"
          >
            <Terminal className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => audioService.playClick()}
            className="p-1 hover:text-cyan-300 transition-colors"
            title="Fullscreen Workspace"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => audioService.playClick()}
            className="p-1 hover:text-cyan-300 transition-colors"
            title="Toggle Panel Layout"
          >
            <SplitSquareVertical className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 2. Middle Content Area */}
      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="absolute inset-0 hud-panel-grid opacity-15 pointer-events-none" />
        
        {activeTab === 'VOICE' && <VoiceTab />}
        {activeTab === 'AGENT' && <AgentTab />}
        {activeTab === 'NOTES' && <NotesTab />}
      </div>

      {/* 3. Bottom Message Composer */}
      <MessageComposer />
    </aside>
  );
};
