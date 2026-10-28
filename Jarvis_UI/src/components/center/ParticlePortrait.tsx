import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { gsap } from 'gsap';
import * as THREE from 'three';

import hologramFragmentShader from '../../shaders/hologram.frag?raw';
import hologramVertexShader from '../../shaders/hologram.vert?raw';
import type { AssistantState } from '../../types/assistant';
import type { CharacterAppearance } from '../../types/modules';
import { backendBridge } from '../../services/backendBridge';
import { SpeechEnvelope } from './hologramSpeech';
import {
  BURST_STRENGTH,
  DIAGONAL_STREAK_WIDTH,
  FEMALE_OPACITY,
  IDLE_JITTER,
  MALE_OPACITY,
  MORPH_DURATION,
  PARTICLE_COUNT,
  SCAN_BAND_WIDTH,
  SCAN_BOTTOM,
  SCAN_DELAY,
  SCAN_DURATION,
  SCAN_TOP,
  STREAK_BRIGHTNESS,
  SWIRL_BIAS,
  SWIRL_STRENGTH,
  type ParticleMorphData,
} from './portraitParticles';

export interface ParticlePortraitHandle {
  switchGender(): void;
}

interface ParticlePortraitProps {
  gender: CharacterAppearance;
  data: ParticleMorphData;
  state: AssistantState;
  onMorphActiveChange?: (active: boolean) => void;
  onGenderChange?: (gender: CharacterAppearance) => void;
}

const CUBIC_IN_OUT = (progress: number): number =>
  progress < 0.5
    ? 4 * progress * progress * progress
    : 1 - Math.pow(-2 * progress + 2, 3) / 2;

export const ParticlePortrait = forwardRef<ParticlePortraitHandle, ParticlePortraitProps>(function ParticlePortrait(
  { gender, data, state, onMorphActiveChange, onGenderChange },
  ref,
) {
  const initialGender = useRef(gender).current;
  const { gl, size } = useThree();
  const geometry = useMemo(() => {
    const result = new THREE.BufferGeometry();
    result.setAttribute('aPosA', new THREE.BufferAttribute(data.femalePositions, 3));
    result.setAttribute('aPosB', new THREE.BufferAttribute(data.malePositions, 3));
    result.setAttribute('aColorA', new THREE.BufferAttribute(data.femaleColors, 3));
    result.setAttribute('aColorB', new THREE.BufferAttribute(data.maleColors, 3));
    result.setAttribute('aSeed', new THREE.BufferAttribute(data.seeds, 1));
    result.setAttribute('aSize', new THREE.BufferAttribute(data.sizes, 1));
    result.setDrawRange(0, PARTICLE_COUNT);
    result.computeBoundingSphere();
    return result;
  }, [data]);

  const initialMix = initialGender === 'male' ? 1 : 0;
  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uMix: { value: initialMix },
      uDirection: { value: 1 },
      uPixelRatio: { value: gl.getPixelRatio() },
      uPointScale: { value: 1 },
      uFemaleOpacity: { value: FEMALE_OPACITY },
      uMaleOpacity: { value: MALE_OPACITY },
      uBurstStrength: { value: BURST_STRENGTH },
      uSwirlStrength: { value: SWIRL_STRENGTH },
      uSwirlBias: { value: SWIRL_BIAS },
      uStreakWidth: { value: DIAGONAL_STREAK_WIDTH },
      uStreakBrightness: { value: STREAK_BRIGHTNESS },
      uScanY: { value: SCAN_TOP },
      uScanActive: { value: 0 },
      uScanBandWidth: { value: SCAN_BAND_WIDTH },
      uIdleJitter: { value: IDLE_JITTER },
      uSpeech: { value: 0 },
      uMouthA: { value: new THREE.Vector2(...data.femaleMouth) },
      uMouthB: { value: new THREE.Vector2(...data.maleMouth) },
    }),
    [data, gl, initialGender, initialMix],
  );

  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        uniforms,
        vertexShader: hologramVertexShader,
        fragmentShader: hologramFragmentShader,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    [uniforms],
  );
  const uniformsRef = useRef(material.uniforms);
  const activeGenderRef = useRef(initialGender);
  const requestedGenderRef = useRef(initialGender);
  const morphingRef = useRef(false);
  const timelineRef = useRef<gsap.core.Timeline | null>(null);
  const elapsedRef = useRef(0);
  const audioClockRef = useRef(0);
  const stateRef = useRef(state);
  const speechRef = useRef(new SpeechEnvelope());
  const onMorphActiveChangeRef = useRef(onMorphActiveChange);
  const onGenderChangeRef = useRef(onGenderChange);
  const reducedMotion = useRef(window.matchMedia('(prefers-reduced-motion: reduce)').matches).current;

  stateRef.current = state;
  onMorphActiveChangeRef.current = onMorphActiveChange;
  onGenderChangeRef.current = onGenderChange;

  useImperativeHandle(ref, () => ({
    switchGender() {
      if (morphingRef.current) return;
      const next = requestedGenderRef.current === 'male' ? 'female' : 'male';
      onGenderChangeRef.current?.(next);
    },
  }));

  useEffect(() => {
    uniformsRef.current.uPixelRatio.value = gl.getPixelRatio();
    uniformsRef.current.uPointScale.value = Math.max(0.65, Math.min(1.6, size.height / 320));
  }, [gl, size.height, size.width]);

  useEffect(() => {
    return backendBridge.onAudioLevel((level) => speechRef.current.noteAudioLevel(level, audioClockRef.current));
  }, []);

  useEffect(() => {
    requestedGenderRef.current = gender;
    if (gender === activeGenderRef.current || morphingRef.current) return;

    timelineRef.current?.kill();
    uniformsRef.current.uScanActive.value = 0;
    uniformsRef.current.uScanY.value = SCAN_TOP;
    uniformsRef.current.uSpeech.value = 0;
    const targetMix = gender === 'male' ? 1 : 0;
    const direction = gender === 'male' ? 1 : -1;

    if (reducedMotion) {
      uniformsRef.current.uMix.value = targetMix;
      activeGenderRef.current = gender;
      onMorphActiveChangeRef.current?.(false);
      return;
    }

    morphingRef.current = true;
    uniformsRef.current.uDirection.value = direction;
    onMorphActiveChangeRef.current?.(true);

    const timeline = gsap.timeline({
      onComplete: () => {
        uniformsRef.current.uMix.value = targetMix;
        activeGenderRef.current = gender;
        morphingRef.current = false;
        onMorphActiveChangeRef.current?.(false);

        const scanTimeline = gsap.timeline();
        scanTimeline.call(() => {
          uniformsRef.current.uScanActive.value = 1;
        }, [], SCAN_DELAY);
        scanTimeline.to(uniformsRef.current.uScanY, {
          value: SCAN_BOTTOM,
          duration: SCAN_DURATION,
          ease: 'none',
        }, SCAN_DELAY);
        scanTimeline.to(uniformsRef.current.uScanActive, {
          value: 0,
          duration: 0.08,
          ease: 'power1.out',
        }, SCAN_DELAY + SCAN_DURATION);
        timelineRef.current = scanTimeline;
      },
    });
    timelineRef.current = timeline;
    timeline.to(uniformsRef.current.uMix, {
      value: targetMix,
      duration: MORPH_DURATION,
      ease: CUBIC_IN_OUT,
    });
  }, [gender, reducedMotion]);

  useEffect(() => {
    return () => {
      timelineRef.current?.kill();
      geometry.dispose();
      material.dispose();
    };
  }, [geometry, material]);

  useFrame((_, delta) => {
    const elapsed = (elapsedRef.current += Math.min(delta, 0.1));
    audioClockRef.current = elapsed;
    uniformsRef.current.uTime.value = elapsed;
    if (reducedMotion) {
      uniformsRef.current.uSpeech.value = 0;
      return;
    }
    const speaking = stateRef.current === 'speaking' && !morphingRef.current;
    uniformsRef.current.uSpeech.value = speechRef.current.update(delta, elapsed, speaking);
  });

  return <points geometry={geometry} material={material} frustumCulled={false} />;
});
