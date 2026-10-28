import React, { useRef, useEffect, useState } from 'react';
import { Settings as SettingsIcon } from 'lucide-react';
import { ThreeHologram } from './ThreeHologram';
import { HologramDebugPanel } from './HologramDebugPanel';
import { TerminateButton } from './TerminateButton';
import { MicrophoneButton } from './MicrophoneButton';
import { useAssistant } from '../../state/assistantStore';
import { useModules } from '../../state/moduleStore';

export const AssistantHologramPanel: React.FC = () => {
  const { displayText, isListening, mode, setMode, state } = useAssistant();
  const { character, openModal, updateCharacter } = useModules();
  const panelRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ w: 341, h: 340 });
  const [characterMorphing, setCharacterMorphing] = useState(false);

  useEffect(() => {
    const updateSize = () => {
      if (panelRef.current) {
        setDimensions({
          w: panelRef.current.clientWidth || 355,
          h: panelRef.current.clientHeight || 356,
        });
      }
    };
    updateSize();
    const panel = panelRef.current;
    if (!panel) return;

    const observer = new ResizeObserver(updateSize);
    observer.observe(panel);
    return () => observer.disconnect();
  }, []);

  const { h } = dimensions;

  return (
    <div className="relative h-full w-full overflow-visible">
      {/* Mode pill floats above the card, exactly like the reference. */}
      <div className="absolute inset-x-0 -top-[31px] z-40 flex h-[25px] items-center justify-center">
        <div className="flex h-full items-center rounded-[4px] border border-[#1c4650] bg-[#03080c] px-0.5 text-[11px] font-mono">
          <button
            onClick={() => setMode('new')}
            className={`flex items-center space-x-1.5 rounded-[3px] px-3 py-0.5 transition-all ${
              mode === 'new'
                ? 'bg-[#16232b] text-slate-100'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${mode === 'new' ? 'bg-cyan-400 shadow-[0_0_6px_#00f0ff]' : 'bg-slate-600'}`} />
            <span className="font-semibold tracking-wide">new</span>
          </button>
          <button
            onClick={() => setMode('classic')}
            className={`flex items-center space-x-1.5 rounded-[3px] px-3 py-0.5 transition-all ${
              mode === 'classic'
                ? 'bg-[#16232b] text-slate-100'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${mode === 'classic' ? 'bg-cyan-400 shadow-[0_0_6px_#00f0ff]' : 'bg-slate-600'}`} />
            <span className="font-semibold tracking-wide">classic</span>
          </button>
        </div>
      </div>

      <button
        onClick={() => openModal('SETTINGS')}
        className="absolute -top-[31px] right-[62px] z-40 flex h-[25px] w-[25px] items-center justify-center rounded-[4px] text-slate-400 transition-colors hover:border-cyan-500 hover:text-cyan-200"
        title="Open Assistant Settings"
        aria-label="Open assistant settings"
      >
        <SettingsIcon className="h-4 w-4" />
      </button>

      {/* Character switch controls the paired source portraits and shared particle draw. */}
      <div className="absolute left-2 top-2 z-40 flex items-center gap-px rounded-full border border-[#1c4650] bg-[#03080c]/95 p-0.5 text-[9px] font-mono">
        {(['male', 'female'] as const).map((appearance) => {
          const selected = character.appearance === appearance;
          return (
            <button
              key={appearance}
              type="button"
              disabled={characterMorphing}
              onClick={() => {
                if (selected || characterMorphing) return;
                setCharacterMorphing(true);
                updateCharacter({ appearance });
              }}
              aria-pressed={selected}
              aria-label={`Use ${appearance} hologram character`}
              className={`rounded-full px-2 py-0.5 uppercase tracking-[0.12em] transition-colors ${
                selected
                  ? 'bg-[#0a222a] text-[#c7f4f8] shadow-[0_0_8px_rgba(0,240,255,0.18)]'
                  : 'text-slate-500 hover:text-slate-200'
              } ${characterMorphing ? 'cursor-not-allowed opacity-50' : ''}`}
            >
              {appearance === 'male' ? 'M' : 'F'}
            </button>
          );
        })}
      </div>

      <div
        ref={panelRef}
        className="relative flex h-full w-full flex-col justify-between overflow-hidden rounded-[12px] border border-[#173d47] bg-[#061019] shadow-[0_0_24px_rgba(0,120,150,0.10)] select-none"
      >
        {/* Trace convergence marker sits on the card edge, like the reference. */}
        <span
          className="pointer-events-none absolute -left-[3px] z-30 h-1.5 w-1.5 rounded-full bg-cyan-400 shadow-[0_0_8px_#00f0ff]"
          style={{ top: `${Math.round(h * 0.64)}px` }}
          aria-hidden="true"
        />

        <div className="pointer-events-none absolute inset-0 z-0 hud-panel-grid opacity-[0.16]" />

        <div className="relative z-10 min-h-0 w-full flex-1">
          <ThreeHologram
            appearance={character.appearance}
            state={state}
            onMorphActiveChange={setCharacterMorphing}
            onGenderChange={(appearance) => updateCharacter({ appearance })}
          />
        </div>

        <HologramDebugPanel />

        <div className="assistant-panel-controls relative z-20 flex shrink-0 flex-col items-center space-y-2.5 pb-3.5">
          <div className="flex items-center space-x-2">
            <span
              className={`h-[5px] w-[5px] rounded-full ${
                isListening
                  ? 'animate-pulse bg-cyan-400 shadow-[0_0_8px_#00f0ff]'
                  : 'bg-emerald-400 shadow-[0_0_8px_#10b981]'
              }`}
            />
            <span className="font-hud text-[12.5px] font-semibold tracking-[0.02em] text-[#dbe7ec]">
              {displayText}
            </span>
          </div>

          <div className="flex items-center space-x-3">
            <TerminateButton />
            <MicrophoneButton />
          </div>
        </div>
      </div>
    </div>
  );
};
