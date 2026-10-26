import React, { useRef, useEffect } from 'react';
import { Bot, User, Copy, Check } from 'lucide-react';
import { useChat } from '../../state/chatStore';
import { audioService } from '../../services/audioService';

export const VoiceTab: React.FC = () => {
  const { messages, isReplying } = useChat();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [copiedId, setCopiedId] = React.useState<string | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isReplying]);

  const handleCopy = (id: string, text: string) => {
    audioService.playClick();
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  // If no messages yet, render the exact "SYSTEM READY" screen from the reference screenshot!
  if (messages.length === 0) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-start px-6 pt-[26px] text-center select-none">
        {/* Robot Icon Badge */}
        <div className="mb-5 flex h-8 w-8 items-center justify-center rounded-md border border-[#2a4a55] bg-[#0a151b]">
          <Bot className="h-4 w-4 text-slate-300" />
        </div>

        {/* System Ready Title */}
        <h3 className="mb-3 text-[13px] font-bold tracking-[0.22em] text-slate-200 uppercase">
          SYSTEM READY
        </h3>

        {/* Multi-language / Regional Greeting */}
        <p className="max-w-[210px] font-sans text-[12px] leading-[1.6] text-slate-500">
          Aapka personal AI assistant.
          <br />
          Bataye main kaise madad kar
          <br />
          sakta hoon?
        </p>
      </div>
    );
  }

  return (
    <div ref={scrollRef} className="min-h-0 min-w-0 flex-1 space-y-4 overflow-y-auto overscroll-contain p-4">
      {messages.map((msg) => {
        const isUser = msg.sender === 'user';
        return (
          <div
            key={msg.id}
            className={`flex items-start space-x-2.5 ${isUser ? 'flex-row-reverse space-x-reverse' : ''}`}
          >
            {/* Avatar */}
            <div
              className={`w-7 h-7 rounded flex items-center justify-center shrink-0 border ${
                isUser
                  ? 'bg-amber-950/40 border-amber-500/40 text-amber-300'
                  : 'bg-cyan-950/40 border-cyan-500/40 text-cyan-300 shadow-[0_0_8px_rgba(0,240,255,0.3)]'
              }`}
            >
              {isUser ? <User className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
            </div>

            {/* Bubble */}
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-xs leading-relaxed border ${
                isUser
                  ? 'bg-amber-950/20 border-amber-500/30 text-amber-100 rounded-tr-none'
                  : 'bg-cyan-950/25 border-cyan-500/30 text-slate-200 rounded-tl-none shadow-[0_0_12px_rgba(0,240,255,0.06)]'
              }`}
            >
              <div className="mb-1 flex flex-wrap items-center justify-between gap-x-2 text-[10px] font-mono text-slate-400">
                <span className="shrink-0 font-semibold text-cyan-400">
                  {isUser ? 'Operator' : 'JARVIS'}
                </span>
                <span className="shrink-0">{msg.timestamp}</span>
              </div>

              <div className="break-words font-sans whitespace-pre-wrap">
                {msg.text}
              </div>

              {!isUser && (
                <div className="mt-2 flex items-center justify-end">
                  <button
                    onClick={() => handleCopy(msg.id, msg.text)}
                    className="text-slate-500 hover:text-cyan-300 p-0.5"
                    title="Copy response"
                  >
                    {copiedId === msg.id ? (
                      <Check className="w-3 h-3 text-emerald-400" />
                    ) : (
                      <Copy className="w-3 h-3" />
                    )}
                  </button>
                </div>
              )}
            </div>
          </div>
        );
      })}

      {/* Streaming Replying Indicator */}
      {isReplying && (
        <div className="flex items-center space-x-2 text-xs text-cyan-400 font-mono animate-pulse pl-9">
          <Bot className="w-4 h-4 animate-spin" />
          <span>Synthesizing response stream...</span>
        </div>
      )}
    </div>
  );
};
