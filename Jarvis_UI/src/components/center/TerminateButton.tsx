import React from 'react';
import { useAssistant } from '../../state/assistantStore';

export const TerminateButton: React.FC = () => {
  const { terminate, state } = useAssistant();
  const isTerminated = state === 'cancelled';

  return (
    <button
      onClick={terminate}
      disabled={isTerminated}
      className={`assistant-terminate-button relative group h-[28px] w-[160px] text-[11px] font-bold tracking-widest uppercase transition-all duration-200 select-none ${
        isTerminated
          ? 'bg-red-950/40 text-red-500/60 border border-red-500/30 cursor-not-allowed opacity-60'
          : 'bg-[#180509]/95 text-[#ff2a55] hover:text-[#ff4d73] border-2 border-[#ff2a55] hover:border-[#ff4d73] hover:bg-[#28080f] shadow-[0_0_15px_rgba(255,42,85,0.4)] hover:shadow-[0_0_25px_rgba(255,42,85,0.7)] active:scale-95'
      }`}
      style={{
        clipPath:
          'polygon(14px 0%, calc(100% - 14px) 0%, 100% 50%, calc(100% - 14px) 100%, 14px 100%, 0% 50%)',
      }}
      title="Emergency Abort — Cancel active tasks and mute voice loop"
    >
      <span className="relative z-10 font-hud font-extrabold tracking-widest">
        {isTerminated ? 'TERMINATED' : 'TERMINATE'}
      </span>
      {/* Subtle interior red pulse */}
      <div className="absolute inset-0 bg-red-600/10 group-hover:bg-red-600/25 transition-colors pointer-events-none" />
    </button>
  );
};
