import React from 'react';
import { Eye, Hand, Maximize2 } from 'lucide-react';
import { ThreeLayeredDiagram } from './ThreeLayeredDiagram';
import { PromptSuggestions } from './PromptSuggestions';
import { VisualHistoryTicker } from './VisualHistoryTicker';
import { useVisualHub } from '../../state/visualHubStore';
import { audioService } from '../../services/audioService';

export const VisualHubPanel: React.FC = () => {
  const { activeTab, setActiveTab, toggleExpanded } = useVisualHub();

  return (
    <div className="hud-panel-frame relative flex h-full min-h-0 w-full flex-col justify-between overflow-hidden">
      {/* Subtle Grid Background */}
      <div className="pointer-events-none absolute inset-0 hud-panel-grid opacity-[0.3]" />

      {/* Decorative Accent Corners */}
      <div className="pointer-events-none absolute left-[6px] top-[6px] h-2.5 w-2.5 border-l border-t border-cyan-400" />
      <div className="pointer-events-none absolute right-[6px] top-[6px] h-2.5 w-2.5 border-r border-t border-cyan-400" />
      <div className="pointer-events-none absolute bottom-[6px] left-[6px] h-2.5 w-2.5 border-b border-l border-cyan-400" />
      <div className="pointer-events-none absolute bottom-[6px] right-[6px] h-2.5 w-2.5 border-b border-r border-cyan-400" />

      {/* Header Bar */}
      <div className="relative z-10 flex h-9 shrink-0 select-none items-center justify-between border-b border-[#18343c] px-3">
        {/* Left: Title & READY Tag */}
        <div className="flex items-center space-x-2">
          <span className="w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_6px_#00f0ff]" />
          <span className="text-xs font-bold tracking-wider text-slate-100 uppercase">
            VISUAL HUB
          </span>
          <span className="text-[10px] font-mono px-1.5 py-0.2 bg-cyan-950/50 border border-cyan-500/30 text-cyan-300 rounded">
            READY
          </span>
        </div>

        {/* Center: Tabs ('visual hub' / 'gesture') */}
        <div className="flex items-center bg-[#050b14]/90 border border-cyan-500/30 rounded-full p-0.5 text-[11px] font-mono">
          <button
            onClick={() => setActiveTab('visual hub')}
            className={`flex items-center space-x-1 px-3 py-0.5 rounded-full transition-all ${
              activeTab === 'visual hub'
                ? 'bg-cyan-950/80 text-cyan-300 border border-cyan-400/40 shadow-[0_0_8px_rgba(0,240,255,0.3)]'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Eye className="w-3 h-3 text-cyan-400" />
            <span>visual hub</span>
          </button>

          <button
            onClick={() => setActiveTab('gesture')}
            className={`flex items-center space-x-1 px-3 py-0.5 rounded-full transition-all ${
              activeTab === 'gesture'
                ? 'bg-cyan-950/80 text-cyan-300 border border-cyan-400/40 shadow-[0_0_8px_rgba(0,240,255,0.3)]'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Hand className="w-3 h-3 text-slate-400" />
            <span>gesture</span>
          </button>
        </div>

        {/* Right: Expand Button */}
        <button
          onClick={() => { audioService.playClick(); toggleExpanded(); }}
          className="text-slate-400 hover:text-cyan-300 transition-colors p-1"
          title="Expand Visual Hub Fullscreen"
        >
          <Maximize2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Main Workspace: Split into Left (3D Diagram) and Right (Prompts) */}
      <div className="relative z-10 grid min-h-0 flex-1 grid-cols-2 overflow-hidden">
        {activeTab === 'visual hub' ? (
          <>
            {/* Left Col: 3D Diagram (5 cols) */}
            <div className="relative col-span-1 h-full">
              <ThreeLayeredDiagram />
            </div>

            {/* Right Col: Prompts (7 cols) */}
            <div className="col-span-1 flex h-full flex-col justify-center">
              <PromptSuggestions />
            </div>
          </>
        ) : (
          /* Gesture Tab Mode */
          <div className="col-span-2 flex h-full flex-col items-center justify-center p-4 text-center">
            <Hand className="w-8 h-8 text-cyan-400/60 mb-2 animate-bounce" />
            <h4 className="text-sm font-semibold text-slate-200">Neural Gesture Tracking</h4>
            <p className="text-xs text-slate-400 mt-1 max-w-sm">
              Computer vision spatial hand-tracking pipeline ready. Connect local camera stream to enable 3D pinch-to-zoom and rotational gestures.
            </p>
          </div>
        )}
      </div>

      {/* Bottom History Strip */}
      <VisualHistoryTicker />
    </div>
  );
};
