import React, { useState, useEffect } from 'react';
import { RefreshCw, Link2, SlidersHorizontal } from 'lucide-react';
import { HeadlineItem } from '../../types/visualHub';
import { audioService } from '../../services/audioService';
import { backendBridge } from '../../services/backendBridge';

interface TodayHeadlinesProps {
  onSelectHeadline: (headline: HeadlineItem) => void;
}

const initialHeadlines: HeadlineItem[] = [
  {
    id: 'hl-1',
    number: '01',
    title: "Tech Innovations Boosting 'Software Ecosystem' Revenue",
    source: 'Silicon Grid News',
    timestamp: '14m ago',
    category: 'Enterprise',
    content: "Global software infrastructure providers reported a 28% year-over-year surge driven by autonomous agent orchestration frameworks and local neural runtime integration."
  },
  {
    id: 'hl-2',
    number: '02',
    title: "Inventor Usman's AI Agents Course Gains Traction",
    source: 'Tech Pioneers Weekly',
    timestamp: '42m ago',
    category: 'Education',
    content: "The specialized advanced agent engineering curriculum has enrolled over 12,000 developers seeking mastery over full-duplex multimodal pipelines and self-healing tool systems."
  },
  {
    id: 'hl-3',
    number: '03',
    title: 'JARVIS Designated as Sci-Fi Living Intelligence',
    source: 'Cybernetics Dispatch',
    timestamp: '1h ago',
    category: 'AI Ethics',
    content: "International computational standards body recognized the autonomous zero-lag interactive HUD as a major leap toward real-time personal holographic assistants."
  },
  {
    id: 'hl-4',
    number: '04',
    title: "Global Markets React to New AI Frameworks",
    source: 'Market Wire Global',
    timestamp: '2h ago',
    category: 'Economy',
    content: "Hardware manufacturers, semiconductor indices, and cloud providers experienced widespread rally as enterprise automation adoption reaches unprecedented scale."
  }
];

export const TodayHeadlines: React.FC<TodayHeadlinesProps> = ({ onSelectHeadline }) => {
  const [headlines, setHeadlines] = useState<HeadlineItem[]>(initialHeadlines);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    backendBridge.fetchHeadlines().then((live) => {
      if (live && live.length > 0) {
        setHeadlines(live);
      }
    });
  }, []);

  const handleRefresh = async () => {
    audioService.playClick();
    setIsRefreshing(true);
    try {
      const live = await backendBridge.fetchHeadlines();
      if (live && live.length > 0) {
        setHeadlines(live);
      } else {
        setHeadlines([...initialHeadlines].reverse());
      }
    } catch {
      setHeadlines([...initialHeadlines].reverse());
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-3 pb-2 pt-2">
      {/* Header Row */}
      <div className="mb-1 flex h-5 items-center justify-between select-none">
        <div className="flex items-center space-x-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_6px_#00f0ff]" />
          <span className="text-[10px] font-bold tracking-[0.16em] text-slate-100 uppercase">
            TODAY HEADLINES
          </span>
        </div>

        {/* Toolbar Icons */}
        <div className="flex items-center space-x-1 text-slate-500">
          <button
            onClick={handleRefresh}
            className={`p-1 hover:text-cyan-300 transition-colors ${isRefreshing ? 'animate-spin text-cyan-400' : ''}`}
            title="Refresh Intelligence Wire"
            aria-label="Refresh headlines"
          >
            <RefreshCw className="w-3 h-3" />
          </button>
          <button
            onClick={() => audioService.playClick()}
            className="p-1 hover:text-cyan-300 transition-colors"
            title="External Source Sync"
            aria-label="Sync external sources"
          >
            <Link2 className="w-3 h-3" />
          </button>
          <button
            onClick={() => audioService.playClick()}
            className="p-1 hover:text-cyan-300 transition-colors"
            title="Filter Categories"
            aria-label="Filter headline categories"
          >
            <SlidersHorizontal className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* Headlines List */}
      <div className="flex-1 select-none divide-y divide-[#16323a] overflow-y-auto pr-1">
        {headlines.map((hl) => (
          <div
            key={hl.id}
            onClick={() => {
              audioService.playClick();
              onSelectHeadline(hl);
            }}
            className="group flex cursor-pointer items-start gap-3 px-1 py-[13px] transition-colors duration-150 hover:bg-[#081820]"
          >
            {/* Number Badge */}
            <span className="font-mono text-[10px] font-semibold text-cyan-400/80 group-hover:text-cyan-300 shrink-0 mt-0.5">
              {hl.number}
            </span>

            {/* Headline Title */}
            <p className="text-[11px] font-medium leading-[1.35] tracking-wide text-slate-300 group-hover:text-cyan-100 line-clamp-2">
              {hl.title}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
};
