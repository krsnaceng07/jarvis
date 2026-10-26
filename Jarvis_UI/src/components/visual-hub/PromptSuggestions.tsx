import React from 'react';
import { useVisualHub } from '../../state/visualHubStore';
import { useChat } from '../../state/chatStore';

export const PromptSuggestions: React.FC = () => {
  const { prompts, selectPrompt, selectedPromptId } = useVisualHub();
  const { sendMessage } = useChat();

  const handlePromptClick = (id: string, title: string) => {
    selectPrompt(id);
    sendMessage(title);
  };

  return (
    <div className="flex flex-col justify-center px-4 py-2">
      {/* Title & Subtitle */}
      <h3 className="text-[15px] font-bold tracking-wide text-slate-100">
        What do you want to see?
      </h3>
      <p className="mb-2.5 mt-1 border-b border-[#14313a] pb-2.5 text-[11.5px] font-normal text-slate-500">
        Ask out loud. Jarvis draws it here as it explains.
      </p>

      {/* 4 Interactive Prompt Rows — plain rows like the reference, not cards */}
      <div className="flex flex-col">
        {prompts.map((p) => {
          const isSelected = selectedPromptId === p.id;
          return (
            <button
              key={p.id}
              onClick={() => handlePromptClick(p.id, p.title)}
              className={`group flex h-[32px] items-center space-x-3 rounded-[2px] px-2 text-left transition-colors ${
                isSelected
                  ? 'bg-cyan-950/40 text-cyan-200'
                  : 'text-slate-300 hover:bg-cyan-950/20 hover:text-cyan-200'
              }`}
            >
              <span className="w-4 shrink-0 font-mono text-[10px] font-semibold text-cyan-500/70 group-hover:text-cyan-300">
                {p.number}
              </span>
              <span className="truncate text-[12.5px] font-medium tracking-wide">
                {p.title}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
