import React from 'react';
import { Newspaper, X, Calendar, ShieldCheck } from 'lucide-react';
import { HeadlineItem } from '../../types/visualHub';

interface HeadlineModalProps {
  headline: HeadlineItem;
  onClose: () => void;
}

export const HeadlineModal: React.FC<HeadlineModalProps> = ({ headline, onClose }) => {
  return (
    <div className="w-[500px] max-w-[90vw] bg-[#070e1c] border border-cyan-500/50 rounded-xl shadow-[0_0_35px_rgba(0,240,255,0.25)] p-5 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-cyan-500/20">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 rounded bg-cyan-950/60 border border-cyan-400 flex items-center justify-center">
            <Newspaper className="w-4 h-4 text-cyan-400" />
          </div>
          <div>
            <span className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest">
              DISPATCH #{headline.number} • {headline.category}
            </span>
            <h3 className="text-sm font-bold text-slate-100 tracking-wide">
              Intelligence Wire Detail
            </h3>
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-cyan-300 p-1"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Article Body */}
      <div className="my-4 space-y-3">
        <h2 className="text-base font-bold text-slate-100 leading-snug">
          {headline.title}
        </h2>

        <div className="flex items-center space-x-3 text-xs text-slate-400 font-mono">
          <span className="flex items-center space-x-1">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>Source: {headline.source}</span>
          </span>
          <span>•</span>
          <span className="flex items-center space-x-1">
            <Calendar className="w-3.5 h-3.5 text-cyan-400" />
            <span>{headline.timestamp}</span>
          </span>
        </div>

        <p className="text-xs text-slate-300 font-sans leading-relaxed pt-2 border-t border-slate-800">
          {headline.content}
        </p>
      </div>

      <div className="pt-3 border-t border-cyan-500/20 flex items-center justify-between">
        <span className="text-[10px] text-slate-500 font-mono">
          Cryptographically Verified Dispatch Hash: 0x7f..9a
        </span>
        <button
          onClick={onClose}
          className="px-4 py-1 bg-cyan-500 hover:bg-cyan-400 text-slate-950 rounded text-xs font-bold transition-colors"
        >
          Close Wire
        </button>
      </div>
    </div>
  );
};
