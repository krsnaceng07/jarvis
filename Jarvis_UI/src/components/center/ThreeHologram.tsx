import { useEffect, useState, type FC } from 'react';

import type { AssistantState } from '../../types/assistant';
import type { CharacterAppearance } from '../../types/modules';
import { HologramScene } from './HologramScene';
import { loadParticlePortraitData, type ParticleMorphData } from './portraitParticles';

interface ThreeHologramProps {
  appearance: CharacterAppearance;
  state?: AssistantState;
  onMorphActiveChange?: (active: boolean) => void;
  onGenderChange?: (appearance: CharacterAppearance) => void;
}

export const ThreeHologram: FC<ThreeHologramProps> = ({
  appearance,
  state = 'idle',
  onMorphActiveChange,
  onGenderChange,
}) => {
  const [particleData, setParticleData] = useState<ParticleMorphData | null>(null);

  useEffect(() => {
    let mounted = true;
    loadParticlePortraitData()
      .then((data) => {
        if (mounted) setParticleData(data);
      })
      .catch((error: unknown) => {
        if (mounted) console.error('[Hologram] portrait particle data could not be created:', error);
      });
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div
      className="relative h-full w-full select-none overflow-hidden pointer-events-none"
      role="img"
      aria-busy={!particleData}
      aria-label={`${appearance} holographic assistant avatar`}
    >
      {particleData && (
        <HologramScene
          appearance={appearance}
          particleData={particleData}
          state={state}
          onMorphActiveChange={onMorphActiveChange}
          onGenderChange={onGenderChange}
        />
      )}
    </div>
  );
};
