import type { FC } from 'react';
import { Canvas } from '@react-three/fiber';
import { PerspectiveCamera } from '@react-three/drei/core/PerspectiveCamera.js';

import type { AssistantState } from '../../types/assistant';
import type { CharacterAppearance } from '../../types/modules';
import { ParticlePortrait } from './ParticlePortrait';
import type { ParticleMorphData } from './portraitParticles';

interface HologramSceneProps {
  appearance: CharacterAppearance;
  particleData: ParticleMorphData;
  state: AssistantState;
  onMorphActiveChange?: (active: boolean) => void;
  onGenderChange?: (appearance: CharacterAppearance) => void;
}

/** One transparent R3F canvas with a single portrait point draw. */
export const HologramScene: FC<HologramSceneProps> = ({
  appearance,
  particleData,
  state,
  onMorphActiveChange,
  onGenderChange,
}) => (
  <div className="relative flex h-full w-full items-center justify-center">
    <Canvas
      dpr={[1, 2]}
      gl={{ alpha: true, antialias: true }}
      style={{ width: 'auto', height: '100%', aspectRatio: '1 / 1', background: 'transparent' }}
    >
      <PerspectiveCamera makeDefault position={[0, 0, 3.4]} fov={35} near={0.1} far={100} />
      <ParticlePortrait
        gender={appearance}
        data={particleData}
        state={state}
        onMorphActiveChange={onMorphActiveChange}
        onGenderChange={onGenderChange}
      />
    </Canvas>
  </div>
);
