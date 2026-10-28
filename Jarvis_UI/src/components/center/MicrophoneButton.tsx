import React from 'react';
import { Mic, MicOff } from 'lucide-react';
import { useAssistant } from '../../state/assistantStore';

export const MicrophoneButton: React.FC = () => {
  const { isListening, isMuted, toggleListening } = useAssistant();

  return (
    <div className="assistant-microphone-wrap relative flex items-center justify-center">
      {/* Active Pulse Ring */}
      {isListening && (
        <div className="absolute w-10 h-10 rounded-full border border-cyan-400/50 animate-ping pointer-events-none" />
      )}

      <button
        type="button"
        onClick={toggleListening}
        aria-label="Microphone mute"
        aria-pressed={isMuted}
        className={`assistant-microphone-button relative z-10 flex h-6 w-6 items-center justify-center rounded-full border transition-all duration-300 ${
          !isMuted
            ? 'bg-cyan-950/60 border-cyan-400 text-cyan-300 shadow-[0_0_15px_rgba(0,240,255,0.6)]'
            : 'bg-[#071324] border-cyan-500/40 text-cyan-400/80 hover:border-cyan-300 hover:text-cyan-200'
        }`}
        title={isMuted ? 'Microphone Muted — Click to activate' : 'Microphone Active — Click to mute'}
      >
        {isMuted ? (
          <MicOff className="h-3 w-3 text-cyan-400" />
        ) : (
          <Mic className={`h-3 w-3 ${isListening ? 'text-cyan-300 animate-pulse' : 'text-cyan-300'}`} />
        )}
      </button>

      <span className="sr-only">{isMuted ? 'Muted' : 'Microphone enabled'}</span>
    </div>
  );
};
