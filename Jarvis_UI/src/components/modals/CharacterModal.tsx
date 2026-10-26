import React, { useEffect, useState } from 'react';
import { useModules } from '../../state/moduleStore';
import { useAssistant } from '../../state/assistantStore';
import { speechService } from '../../services/speechService';
import type { CharacterAppearance } from '../../types/modules';
import { ThreeHologram } from '../center/ThreeHologram';

interface VoicePreset {
  id: string;
  name: string;
  description: string;
  sample: string;
  voiceId: string;
}

const VOICE_PRESETS: Record<CharacterAppearance, VoicePreset[]> = {
  female: [
    {
      id: 'girlfriend',
      name: 'Girlfriend',
      description: 'Flirty, teasing & romantic',
      sample: 'Hey, you. I was just thinking about you. What are we doing today?',
      voiceId: 'Companion / Feminine',
    },
    {
      id: 'assistant',
      name: 'Assistant',
      description: 'Sharp chief-of-staff energy',
      sample: 'Good morning. Your priorities are ready whenever you are.',
      voiceId: 'Assistant / Feminine',
    },
    {
      id: 'best-friend',
      name: 'Best Friend',
      description: 'Fun, honest & always hyping you',
      sample: 'Okay, tell me everything. I am all ears.',
      voiceId: 'Best friend / Feminine',
    },
  ],
  male: [
    {
      id: 'jarvis',
      name: 'Jarvis',
      description: 'Calm, precise & always at your service',
      sample: 'At your service. How can I help today?',
      voiceId: 'Assistant / Masculine',
    },
    {
      id: 'bro',
      name: 'Bro',
      description: 'Casual, funny & on your side',
      sample: 'You have got this. I am right here with you.',
      voiceId: 'Best friend / Masculine',
    },
    {
      id: 'mentor',
      name: 'Mentor',
      description: 'Clear, steady & motivating',
      sample: 'Take a breath. Let us work through the next step together.',
      voiceId: 'Mentor / Masculine',
    },
  ],
};

const TONES = [
  'Professional & Sci-Fi',
  'Concise & Technical',
  'Warm & Conversational',
] as const;

export const CharacterModal: React.FC = () => {
  const { character, updateCharacter, closeModal } = useModules();
  const { setSystemName } = useAssistant();
  const [step, setStep] = useState<3 | 4>(3);
  const [selectedVoice, setSelectedVoice] = useState<string | null>(() =>
    VOICE_PRESETS[character.appearance].find((voice) => voice.name === character.role)?.id ?? null,
  );
  const [name, setName] = useState(character.name);
  const [tone, setTone] = useState(character.tone);
  const [speed, setSpeed] = useState(character.speed);
  const [pitch, setPitch] = useState(character.pitch);

  useEffect(() => () => speechService.cancelSpeech(), []);

  const selectAppearance = (appearance: CharacterAppearance) => {
    if (appearance === character.appearance) return;
    setSelectedVoice(null);
    updateCharacter({ appearance });
  };

  const selectVoice = (voice: VoicePreset) => {
    setSelectedVoice(voice.id);
    updateCharacter({ role: voice.name, voiceId: voice.voiceId });
    speechService.speak(voice.sample);
  };

  const handleContinue = () => setStep(4);

  const handleSave = (event: React.FormEvent) => {
    event.preventDefault();
    updateCharacter({ name, tone, speed, pitch });
    setSystemName(name);
    closeModal();
  };

  const voices = VOICE_PRESETS[character.appearance];

  return (
    <div className="fixed inset-0 z-[100] flex h-[100dvh] min-h-0 flex-col overflow-y-auto bg-[#02070b] text-slate-100 font-hud">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_72%_47%,rgba(0,91,133,0.11),transparent_37%),radial-gradient(ellipse_at_19%_52%,rgba(0,50,68,0.08),transparent_43%)]" />

      <header className="relative z-10 flex h-9 shrink-0 items-center px-6 sm:px-9">
        <div className="flex items-center gap-3 text-[11px] font-bold tracking-[0.32em] text-slate-200">
          <span className="text-[13px] tracking-[0.25em]">JARVIS</span>
          <span className="h-3.5 w-px bg-slate-600/70" />
          <span className="text-cyan-300 tracking-[0.32em]">KRISHNA</span>
        </div>
      </header>

      <main className="relative z-10 mx-auto grid min-h-0 w-full max-w-[1480px] flex-1 grid-cols-1 items-center gap-5 px-6 pb-14 pt-3 sm:px-9 lg:grid-cols-[minmax(350px,0.72fr)_minmax(0,1.2fr)] lg:gap-10 xl:gap-16">
        {step === 3 ? (
          <section className="relative z-10 mx-auto w-full max-w-[430px] py-5 lg:mx-0 lg:py-0">
            <div className="mb-3 text-[10px] font-bold tracking-[0.28em] text-cyan-300">STEP 3 OF 8</div>
            <h1 className="mb-5 text-[clamp(23px,2vw,30px)] font-medium leading-[1.1] tracking-[0.01em] text-[#e6edf3]">
              I have no voice yet. Choose one.
            </h1>

            <div role="group" aria-label="Choose a hologram character" className="grid grid-cols-2 gap-2">
              {(['female', 'male'] as const).map((appearance) => {
                const selected = character.appearance === appearance;
                return (
                  <button
                    key={appearance}
                    type="button"
                    onClick={() => selectAppearance(appearance)}
                    aria-pressed={selected}
                    className={`h-10 border text-[12px] font-bold tracking-[0.28em] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300 ${
                      selected
                        ? 'border-[#5c8791] bg-[#12313a]/55 text-slate-100'
                        : 'border-[#28444b] bg-[#050c11]/75 text-[#a8bbc1] hover:border-[#4d7780] hover:text-slate-100'
                    }`}
                  >
                    {appearance.toUpperCase()}
                  </button>
                );
              })}
            </div>

            <p className="mb-3 mt-5 text-[12px] text-[#96a3aa]">Now pick a character. Click one to hear it.</p>

            <div className="mb-1 flex items-center gap-2" aria-hidden="true">
              <span className="h-px flex-1 bg-[#26383e]" />
              <span className="text-[9px] font-bold tracking-[0.18em] text-[#60d7e6]">RECOMMENDED</span>
              <span className="w-3 h-px bg-[#26383e]" />
            </div>

            <div className="border-t border-[#203138]">
              {voices.map((voice) => {
                const selected = selectedVoice === voice.id;
                return (
                  <div
                    key={voice.id}
                    className={`group flex min-h-[42px] items-center gap-3 border-b border-[#203138] px-4 transition-colors ${
                      selected ? 'bg-[#0b2028]/65' : 'hover:bg-[#08161c]/80'
                    }`}
                  >
                    <button
                      type="button"
                      aria-pressed={selected}
                      onClick={() => selectVoice(voice)}
                      className="flex min-w-0 flex-1 items-center gap-3 text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-cyan-300"
                    >
                      <span className={`w-[97px] shrink-0 text-[14px] font-semibold ${selected ? 'text-[#e7f4f6]' : 'text-[#c5cdd1]'}`}>
                        {voice.name}
                      </span>
                      <span className="min-w-0 flex-1 text-[11px] leading-4 text-[#778990]">{voice.description}</span>
                    </button>
                    <button
                      type="button"
                      aria-label={`Play ${voice.name} voice sample`}
                      onClick={() => selectVoice(voice)}
                      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[#35616b] text-[#54d9e7] transition-colors hover:border-[#7ceaf4] hover:bg-cyan-950/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300"
                    >
                      <span className="ml-0.5 text-[10px]" aria-hidden="true">▶</span>
                    </button>
                  </div>
                );
              })}
            </div>

            <div className="mt-7 flex items-center gap-3">
              <button
                type="button"
                disabled={!selectedVoice}
                onClick={handleContinue}
                className={`h-10 min-w-[150px] border px-5 text-[11px] font-extrabold tracking-[0.23em] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300 ${
                  selectedVoice
                    ? 'border-[#57909a] bg-[#10242a]/80 text-[#d9f5f7] hover:border-cyan-300 hover:bg-[#13323a]'
                    : 'cursor-not-allowed border-[#334148] bg-[#091015]/80 text-[#59646b]'
                }`}
              >
                CONTINUE
              </button>
              <button
                type="button"
                onClick={closeModal}
                className="h-9 border-l border-[#36535b] px-4 text-[10px] font-bold tracking-[0.2em] text-[#a8bbc1] transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300"
              >
                BACK
              </button>
            </div>
          </section>
        ) : (
          <section className="relative z-10 mx-auto w-full max-w-[430px] py-5 lg:mx-0 lg:py-0">
            <div className="mb-3 text-[10px] font-bold tracking-[0.28em] text-cyan-300">STEP 4 OF 8</div>
            <h1 className="mb-2 text-[clamp(24px,2.2vw,32px)] font-semibold leading-[1.05] tracking-wide text-[#e6edf3]">
              Make it yours.
            </h1>
            <p className="mb-6 text-[12px] text-[#96a3aa]">Tune the voice and personality for {character.role}.</p>

            <form onSubmit={handleSave} className="space-y-5 text-[12px]">
              <label className="block space-y-2">
                <span className="font-semibold text-slate-300">Assistant name</span>
                <input
                  type="text"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  className="h-10 w-full select-text border border-[#28444b] bg-[#050c11] px-3 text-slate-100 outline-none focus:border-cyan-400"
                />
              </label>

              <label className="block space-y-2">
                <span className="font-semibold text-slate-300">Communication tone</span>
                <select
                  value={tone}
                  onChange={(event) => setTone(event.target.value as typeof TONES[number])}
                  className="h-10 w-full border border-[#28444b] bg-[#050c11] px-3 text-slate-100 outline-none focus:border-cyan-400"
                >
                  {TONES.map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
              </label>

              <div className="grid grid-cols-2 gap-5">
                <label className="block space-y-2">
                  <span className="flex justify-between font-semibold text-slate-300"><span>Speech rate</span><span className="text-cyan-300">{speed.toFixed(2)}x</span></span>
                  <input type="range" min="0.8" max="1.5" step="0.05" value={speed} onChange={(event) => setSpeed(Number(event.target.value))} className="w-full accent-cyan-400" />
                </label>
                <label className="block space-y-2">
                  <span className="flex justify-between font-semibold text-slate-300"><span>Voice pitch</span><span className="text-cyan-300">{pitch.toFixed(2)}</span></span>
                  <input type="range" min="0.7" max="1.3" step="0.05" value={pitch} onChange={(event) => setPitch(Number(event.target.value))} className="w-full accent-cyan-400" />
                </label>
              </div>

              <div className="border-t border-[#203138] pt-4">
                <div className="mb-2 font-semibold text-slate-300">Core behavioral directives</div>
                <div className="flex flex-wrap gap-2">
                  {character.personalityTraits.map((trait) => (
                    <span key={trait} className="border border-[#34525a] bg-[#09141a] px-2 py-1 text-[10px] text-[#a9c0c6]">{trait}</span>
                  ))}
                </div>
              </div>

              <div className="flex items-center gap-3 border-t border-[#203138] pt-5">
                <button type="button" onClick={() => setStep(3)} className="h-9 border-l border-[#36535b] px-4 text-[10px] font-bold tracking-[0.2em] text-[#a8bbc1] hover:text-white">BACK</button>
                <button type="submit" className="h-10 min-w-[150px] border border-[#57909a] bg-[#10242a]/80 px-5 text-[11px] font-extrabold tracking-[0.23em] text-[#d9f5f7] hover:border-cyan-300 hover:bg-[#13323a]">CONTINUE</button>
              </div>
            </form>
          </section>
        )}

        <section aria-label={`${character.appearance} particle hologram preview`} className={`relative mx-auto flex w-full items-center justify-center ${step === 3 ? 'max-w-[min(72vw,72vh)]' : 'max-w-[min(56vw,58vh)]'} aspect-square`}>
          <div className="absolute inset-0 rounded-full bg-[radial-gradient(circle,rgba(0,154,219,0.12),rgba(0,48,71,0.045)_53%,transparent_71%)] blur-md" />
          <svg viewBox="0 0 600 600" className="absolute inset-0 h-full w-full overflow-visible" aria-hidden="true">
            <circle cx="300" cy="300" r="270" fill="none" stroke="#17434c" strokeWidth="1" strokeOpacity="0.55" />
            <circle cx="300" cy="300" r="281" fill="none" stroke="#16404a" strokeWidth="1" strokeOpacity="0.44" />
            {Array.from({ length: 88 }, (_, index) => {
              const angle = (index / 88) * Math.PI * 2 - Math.PI / 2;
              const major = index % 11 === 0;
              const inner = major ? 287 : 291;
              const outer = major ? 300 : 296;
              return (
                <line
                  key={index}
                  x1={300 + Math.cos(angle) * inner}
                  y1={300 + Math.sin(angle) * inner}
                  x2={300 + Math.cos(angle) * outer}
                  y2={300 + Math.sin(angle) * outer}
                  stroke={major ? '#28616c' : '#1b4650'}
                  strokeWidth={major ? 1.5 : 1}
                  strokeOpacity={major ? 0.72 : 0.55}
                />
              );
            })}
          </svg>
          <div className="absolute inset-[5.5%] overflow-hidden rounded-full">
            <ThreeHologram appearance={character.appearance} framing="preview" />
          </div>
        </section>
      </main>

      <footer className="pointer-events-none absolute bottom-5 left-6 z-10 flex gap-[3px] sm:left-9" aria-label={`Onboarding step ${step} of 8`}>
        {Array.from({ length: 8 }, (_, index) => {
          const completed = index + 1 < step;
          const current = index + 1 === step;
          return <span key={index} className={`h-[2px] w-[27px] sm:w-[30px] ${completed ? 'bg-[#397884]' : current ? 'bg-[#d9fbff] shadow-[0_0_8px_rgba(102,235,247,0.85)]' : 'bg-[#263a40]'}`} />;
        })}
      </footer>

      <div className="pointer-events-none absolute bottom-3 right-6 z-10 sm:right-9">
        <span className="flex h-8 items-center gap-2 bg-[#071017]/90 px-3 text-[10px] text-[#7f9299]">
          <span aria-hidden="true">♪×</span> Music off
        </span>
      </div>
    </div>
  );
};
