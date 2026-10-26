import React, { useState, useRef, useEffect } from 'react';
import { Paperclip, ArrowUp, Loader2, Mic } from 'lucide-react';
import { useChat } from '../../state/chatStore';
import { useAssistant } from '../../state/assistantStore';
import { audioService } from '../../services/audioService';
import { backendBridge } from '../../services/backendBridge';

export const MessageComposer: React.FC = () => {
  const [input, setInput] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const wasTranscribingRef = useRef(false);
  const { sendMessage, isReplying, addMessage, liveInputText, isLiveTranscribing } = useChat();
  const { systemName } = useAssistant();

  // Real-time synchronization of spoken speech into the chat input box
  useEffect(() => {
    if (isLiveTranscribing) {
      setInput(liveInputText);
      wasTranscribingRef.current = true;
    } else if (wasTranscribingRef.current && !isLiveTranscribing) {
      // Speech finished and committed as a single full sentence; reset input box
      setInput('');
      wasTranscribingRef.current = false;
    }
  }, [liveInputText, isLiveTranscribing]);

  const handleSend = () => {
    if (!input.trim() || isReplying || isUploading) return;
    sendMessage(input);
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleAttachmentClick = () => {
    audioService.playClick();
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    audioService.playActivate();
    setIsUploading(true);
    addMessage('user', `📎 Attaching file: ${file.name}`);

    try {
      const res = await backendBridge.uploadFile(file);
      if (res.success) {
        addMessage('assistant', `Received attached file: ${res.filename || file.name}. I am analyzing its content for you, Sir.`);
      } else {
        addMessage('assistant', `⚠️ Upload failed: ${res.error || 'Server error'}`);
      }
    } catch (err: any) {
      addMessage('assistant', `⚠️ Upload error: ${err?.message || 'Network error'}`);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  return (
    <div className="relative z-10 shrink-0 select-none border-t border-[#18343c] bg-[#050d13] p-3">
      {/* Hidden file input */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        className="hidden"
        accept="image/*,.txt,.pdf,.py,.json,.md,.csv"
      />

      <div
        className={`relative flex h-[46px] items-center rounded-[10px] border bg-[#0a1620] px-3 transition-all ${
          isLiveTranscribing
            ? 'border-cyan-400 shadow-[0_0_14px_rgba(0,240,255,0.3)] ring-1 ring-cyan-400/50'
            : 'border-[#244653] focus-within:border-[#4f929f]'
        }`}
      >
        {/* Live Voice Indicator when user speaks */}
        {isLiveTranscribing && (
          <div className="flex items-center space-x-1.5 mr-2 shrink-0 animate-pulse">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-400"></span>
            </span>
            <Mic className="w-3 h-3 text-cyan-400" />
            <span className="text-[10px] font-mono text-cyan-300 font-bold uppercase tracking-wider hidden sm:inline">
              Voice Input
            </span>
          </div>
        )}

        {/* Text Input */}
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            isLiveTranscribing
              ? 'Speaking... writing speech in real time...'
              : `Type to ${systemName} Voice...`
          }
          className="flex-1 bg-transparent text-xs text-slate-100 placeholder:text-slate-500 focus:outline-none font-sans pr-2"
        />

        {/* Attachment Paperclip Button */}
        <button
          onClick={handleAttachmentClick}
          disabled={isUploading}
          className="text-slate-400 hover:text-cyan-300 p-1 mr-1 transition-colors disabled:opacity-50"
          title="Attach file, document, or image"
        >
          {isUploading ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin text-cyan-400" />
          ) : (
            <Paperclip className="w-3.5 h-3.5" />
          )}
        </button>

        {/* Send Up-Arrow Button */}
        <button
          onClick={handleSend}
          disabled={!input.trim() || isReplying || isUploading}
          className={`w-7 h-7 rounded-full flex items-center justify-center transition-all ${
            input.trim() && !isReplying && !isUploading
              ? 'bg-cyan-500 hover:bg-cyan-400 text-slate-950 shadow-[0_0_8px_#00f0ff] cursor-pointer'
              : 'bg-slate-800 text-slate-500 cursor-not-allowed'
          }`}
          title="Send message (Enter)"
        >
          <ArrowUp className="w-3.5 h-3.5 stroke-[2.5]" />
        </button>
      </div>
    </div>
  );
};
