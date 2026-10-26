import React from 'react';
import { BookOpen, Image as ImageIcon, Music, Cpu } from 'lucide-react';
import { useVisualHub } from '../../state/visualHubStore';
import { audioService } from '../../services/audioService';

export const VisualHistoryTicker: React.FC = () => {
  const { historyItems } = useVisualHub();

  const getThumbnailIcon = (type: string) => {
    switch (type) {
      case 'audio':
        return <Music className="w-3 h-3 text-cyan-400" />;
      case 'blueprint':
      case 'diagram':
        return <Cpu className="w-3 h-3 text-emerald-400" />;
      default:
        return <ImageIcon className="w-3 h-3 text-cyan-400" />;
    }
  };

  return (
    <div className="w-full h-8 bg-[#040812] border-t border-cyan-500/20 px-3 flex items-center space-x-3 overflow-x-auto select-none no-scrollbar">
      {/* Library Label Tag */}
      <div className="flex items-center space-x-1.5 text-[10px] font-bold tracking-wider text-cyan-400 uppercase shrink-0">
        <BookOpen className="w-3 h-3" />
        <span>LIBRARY</span>
      </div>

      {/* History Items Horizontal List */}
      <div className="flex items-center space-x-2 overflow-x-auto text-[11px] font-mono shrink-0">
        {historyItems.map((item) => (
          <div
            key={item.id}
            onClick={() => audioService.playClick()}
            className="flex items-center space-x-1.5 px-2 py-0.5 rounded bg-slate-900/60 hover:bg-cyan-950/40 border border-cyan-500/15 hover:border-cyan-400/40 text-slate-300 hover:text-cyan-300 cursor-pointer transition-colors shrink-0"
            title={`${item.title} (${item.category} - ${item.date})`}
          >
            {getThumbnailIcon(item.thumbnailType)}
            <span className="truncate max-w-[110px] text-slate-300">
              {item.title}
            </span>
            <span className="text-slate-500 text-[10px]">
              {item.date}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
