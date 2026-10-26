import React, { useEffect, useRef, useState } from 'react';
import { BookOpen, Brain, Settings as SettingsIcon, Shield } from 'lucide-react';
import { useModules } from '../../state/moduleStore';
import type { ModuleId } from '../../types/modules';

const MODULES: ModuleId[] = ['MEMORY', 'SKILLS', 'CHARACTER', 'SETTINGS'];

const ENTRY_LEVELS = [161 / 356, 178 / 356, 190 / 356, 205 / 356];
const TRACE_COLORS = ['#37c6d8', '#38c78c', '#e35b6a', '#a7b6c0'];

const getModuleStyle = (id: ModuleId) => {
  switch (id) {
    case 'MEMORY':
      return {
        icon: <Brain className="h-4 w-4 text-[#54d8e6]" />,
        box: 'border-[#28616b] bg-[#0a1b24] hover:bg-[#0d242e]',
        iconBox: 'border-[#285b65] bg-[#0d2530]',
        dot: 'bg-[#49d7e7] shadow-[0_0_7px_rgba(73,215,231,0.45)]',
      };
    case 'SKILLS':
      return {
        icon: <BookOpen className="h-4 w-4 text-[#50d59c]" />,
        box: 'border-[#285944] bg-[#0a1b16] hover:bg-[#0e261d]',
        iconBox: 'border-[#27563f] bg-[#0d251c]',
        dot: 'bg-[#50d59c] shadow-[0_0_7px_rgba(80,213,156,0.4)]',
      };
    case 'CHARACTER':
      return {
        icon: <Shield className="h-4 w-4 text-[#e8707e]" />,
        box: 'border-[#6e343d] bg-[#201115] hover:bg-[#2a151b]',
        iconBox: 'border-[#66303a] bg-[#2a151a]',
        dot: 'bg-[#e8707e] shadow-[0_0_7px_rgba(232,112,126,0.4)]',
      };
    case 'SETTINGS':
      return {
        icon: <SettingsIcon className="h-4 w-4 text-[#b5c1ca]" />,
        box: 'border-[#46535d] bg-[#111a23] hover:bg-[#18232e]',
        iconBox: 'border-[#45535d] bg-[#17212b]',
        dot: 'bg-[#b5c1ca] shadow-[0_0_7px_rgba(181,193,202,0.35)]',
      };
  }
};

export const ModuleConnectorStack: React.FC = () => {
  const { modules, openModal } = useModules();
  const rootRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(356);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const measure = () => setHeight(Math.round(root.getBoundingClientRect().height));
    const observer = new ResizeObserver(measure);
    observer.observe(root);
    measure();
    return () => observer.disconnect();
  }, []);

  const stackHeight = Math.min(247, height);
  const firstCardCenter = (height - stackHeight) / 2 + 21.5 + 15;
  const cardGap = (stackHeight - 43) / 3;
  const cardCenters = Array.from({ length: 4 }, (_, index) =>
    Math.round(firstCardCenter + index * cardGap),
  );
  const traces = TRACE_COLORS.map((color, index) => {
    const cardCenter = cardCenters[index];
    const entryY = Math.round(height * ENTRY_LEVELS[index]);
    const elbowX = index === 0 || index === 3 ? 46 : 56;

    return {
      color,
      startY: cardCenter,
      endY: entryY,
      path: `M 2 ${cardCenter} L ${elbowX} ${cardCenter} L 84 ${entryY} L 110 ${entryY}`,
    };
  });

  return (
    <div ref={rootRef} className="relative flex h-full w-full items-center select-none">
      <div className="relative z-20 flex h-[min(247px,100%)] w-[160px] shrink-0 flex-col justify-between">
        {MODULES.map((id) => {
          const module = modules[id];
          const style = getModuleStyle(id);

          return (
            <button
              key={id}
              type="button"
              onClick={() => openModal(id)}
              aria-label={`${module.label}: ${module.statusLabel}`}
              className={`group flex h-[43px] w-[160px] shrink-0 items-center justify-between border px-2 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-cyan-200 ${style.box}`}
              style={{ clipPath: 'polygon(9px 0, calc(100% - 9px) 0, 100% 9px, 100% calc(100% - 9px), calc(100% - 9px) 100%, 9px 100%, 0 calc(100% - 9px), 0 9px)' }}
              title={`${module.label} Subsystem — ${module.statusLabel}`}
            >
              <span className="flex items-center gap-2.5">
                <span className={`flex h-7 w-7 shrink-0 items-center justify-center border ${style.iconBox}`}>
                  {style.icon}
                </span>
                <span className="font-hud text-[12px] font-bold tracking-[0.1em] text-[#e0e9ed]">
                  {module.label}
                </span>
              </span>
              <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${style.dot} transition-transform group-hover:scale-125`} />
            </button>
          );
        })}
      </div>

      <svg
        className="relative z-10 h-full min-w-0 flex-1 -ml-px overflow-visible"
        viewBox={`0 0 110 ${height}`}
        preserveAspectRatio="none"
        fill="none"
        aria-hidden="true"
      >
        <defs>
          <filter id="module-trace-glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="1.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {traces.map(({ color, path, startY, endY }) => (
          <g key={path}>
            <path d={path} stroke={color} strokeWidth="1.6" strokeOpacity="0.8" filter="url(#module-trace-glow)" />
            <path d={path} stroke="#d9fbff" strokeWidth="1.5" strokeOpacity="0.55" strokeDasharray="4 90" className="animate-trace-flow" />
            <circle cx="2" cy={startY} r="2.2" fill={color} />
            <circle cx="108" cy={endY} r="2.6" fill={color} />
          </g>
        ))}
      </svg>
    </div>
  );
};
