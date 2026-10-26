import React, { useState } from 'react';
import { RefreshCw, Maximize2, LayoutGrid } from 'lucide-react';
import { GlobeMapCanvas } from './GlobeMapCanvas';
import { TodayHeadlines } from './TodayHeadlines';
import { HeadlineItem } from '../../types/visualHub';
import { audioService } from '../../services/audioService';

interface SatLinkFeedProps {
  onSelectHeadline: (headline: HeadlineItem) => void;
  onExpandMap: () => void;
}

export const SatLinkFeed: React.FC<SatLinkFeedProps> = ({
  onSelectHeadline,
  onExpandMap,
}) => {
  const [is3D, setIs3D] = useState(true);
  const [activeNav, setActiveNav] = useState('Today');
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleRefresh = () => {
    audioService.playClick();
    setIsRefreshing(true);
    setTimeout(() => setIsRefreshing(false), 500);
  };

  return (
    <aside className="hud-panel-frame flex h-full w-full min-h-0 flex-col overflow-hidden select-none">
      {/* 1. Main Header: SAT-LINK FEED */}
      <div className="flex h-[31px] shrink-0 items-center justify-between border-b border-[#18343c] px-3">
        <div className="flex items-center space-x-2">
          <span className="w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_6px_#00f0ff]" />
          <h2 className="text-[11px] font-bold tracking-[0.16em] text-slate-100 uppercase">
            SAT-LINK FEED
          </h2>
        </div>
        <button
          onClick={() => audioService.playClick()}
          className="text-slate-500 transition-colors hover:text-cyan-300 p-1"
          title="Grid Layout View"
          aria-label="Grid layout view"
        >
          <LayoutGrid className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* 2. Subheader: SATELLITE STREAM, EXPAND and the 2D/3D switch share one row */}
      <div className="flex h-[30px] shrink-0 items-center justify-between border-b border-[#18343c] bg-[#050d13] px-3">
        <div className="flex items-center space-x-2">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_6px_#10b981]" />
          <span className="text-[10px] font-semibold tracking-[0.14em] text-slate-300 uppercase">
            SATELLITE STREAM
          </span>
          <button
            onClick={handleRefresh}
            className={`text-slate-500 hover:text-cyan-300 ml-1 p-0.5 ${isRefreshing ? 'animate-spin text-cyan-400' : ''}`}
            title="Refresh Orbital Link"
            aria-label="Refresh orbital link"
          >
            <RefreshCw className="w-2.5 h-2.5" />
          </button>
        </div>

        <button
          onClick={() => { audioService.playClick(); onExpandMap(); }}
          className="flex items-center space-x-1 rounded-[3px] border border-[#1c4650] px-1.5 py-[2px] text-[9px] font-semibold tracking-[0.14em] text-cyan-300 uppercase transition-colors hover:border-cyan-500 hover:text-cyan-100"
        >
          <Maximize2 className="w-2.5 h-2.5" />
          <span>EXPAND</span>
        </button>
      </div>

      {/* 3. Map mode switch overlays the globe's top-right corner, like the reference */}
      <div className="relative flex min-h-0 flex-[1.41] flex-col overflow-hidden">
        <div className="absolute right-3 top-2 z-20 flex items-center space-x-1.5">
          <div className="flex items-center space-x-1 rounded-[3px] border border-[#1c4650] bg-[#040b10]/90 p-px text-[9px] font-mono">
            <button
              onClick={() => { audioService.playClick(); setIs3D(false); }}
              className={`px-1.5 py-[1px] rounded-[2px] transition-colors ${
                !is3D ? 'bg-emerald-400 font-bold text-[#04120b]' : 'text-slate-500 hover:text-slate-200'
              }`}
            >
              2D
            </button>
            <button
              onClick={() => { audioService.playClick(); setIs3D(true); }}
              className={`px-1.5 py-[1px] rounded-[2px] transition-colors ${
                is3D ? 'bg-emerald-400 font-bold text-[#04120b]' : 'text-slate-500 hover:text-slate-200'
              }`}
            >
              3D
            </button>
          </div>

          <button
            onClick={() => { audioService.playClick(); onExpandMap(); }}
            className="flex h-[18px] w-[18px] items-center justify-center rounded-[3px] border border-[#1c4650] bg-[#040b10]/90 text-slate-400 transition-colors hover:border-cyan-500 hover:text-cyan-200"
            title="Expand satellite map"
            aria-label="Expand satellite map"
          >
            <Maximize2 className="w-2.5 h-2.5" />
          </button>
        </div>

        <GlobeMapCanvas
          is3D={is3D}
          activeNav={activeNav}
          onNavChange={(nav) => setActiveNav(nav)}
        />
      </div>

      {/* 5. Today Headlines (shares the rail frame, separated by a border) */}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden border-t border-[#18343c]">
        <TodayHeadlines onSelectHeadline={onSelectHeadline} />
      </div>
    </aside>
  );
};
