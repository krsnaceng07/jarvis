import React, { useEffect, useRef } from 'react';

import * as THREE from 'three';

import type { AssistantState } from '../../types/assistant';
import type { CharacterAppearance } from '../../types/modules';

import { hologramDebug } from './hologramDebug';
import { buildCloud, CLOUD_URLS, computeFaceAnchors, mulberry32, type AvatarCloud } from './hologramCloud';
import {
  BAND_END_Y,
  REVEAL_SECONDS,
  sampleDissolve,
  sampleHologramTimeline,
} from './hologramTimeline';
import { SpeechEnvelope } from './hologramSpeech';
import { backendBridge } from '../../services/backendBridge';

interface ThreeHologramProps {
  appearance: CharacterAppearance;
  framing?: 'panel' | 'preview';
  state?: AssistantState;
}

const CAMERA_FOV = 35;
const CAMERA_Z = 3.4;
// Must stay above the baked particle count (male bake is ~37k).
const CAPACITY = 42000;

// Measured from the reference card: the bust fills ~65% of the panel width and
// sits in the upper 68% so the status row and TERMINATE button stay clear.
const PANEL_FIT_MARGIN = 1.55;
const PANEL_LIFT = 0.227;

const TAU = Math.PI * 2;

/**
 * Sprite size and per-point opacity, calibrated against the storyboard bust on a
 * 662x548 device-pixel canvas: lit p50 ~62, p90 ~118, clipped <0.1%, which is
 * where the reference sits (59 / 123 / ~0%). Larger sprites raise silhouette
 * correlation but blur the filament strokes the art is made of; smaller ones
 * turn every particle into a hard dot (confetti).
 */
const RENDER_STYLE: Record<CharacterAppearance, { size: number; opacity: number }> = {
  male: { size: 3.6, opacity: 0.82 },
  female: { size: 3.6, opacity: 0.82 },
};

type Stage = 'reveal' | 'idle' | 'dissolve';

const VERTEX_SHADER = `
  attribute vec3 aColor;
  attribute float aAlpha;
  attribute float aScale;
  attribute float aPhase;
  attribute vec3 aScatter;
  attribute float aSeed;

  uniform float uTime;
  uniform float uPixelRatio;
  uniform float uSize;
  uniform float uScatter;
  uniform float uTurbo;
  uniform float uBrightness;
  uniform float uSpeech;

  uniform float uBandY;
  uniform float uBandStrength;
  uniform float uBandOn;

  uniform float uFaceX;
  uniform float uHeadY;
  uniform float uMouthY;
  uniform float uYaw;
  uniform float uPitch;
  uniform float uRoll;
  uniform float uBreath;
  uniform float uSway;

  varying vec3 vColor;
  varying float vAlpha;

  void main() {
    vec3 pos = position;

    // ---- living body -----------------------------------------------------
    // Breathing lifts the chest and shoulders; the head keeps its own rig so
    // torso motion never drags the face around.
    float head = smoothstep(uHeadY - 0.10, uHeadY + 0.20, position.y);
    float torso = 1.0 - head;

    float breathe = uBreath * torso;
    pos.y += breathe * 0.030 * smoothstep(-0.75, 0.55, position.y);
    pos.x *= 1.0 + breathe * 0.018;
    pos.z += breathe * 0.020;

    // Weight shift from the base of the bust, plus a slow shoulder roll.
    pos.x += uSway * (0.026 + 0.05 * clamp((position.y + 1.15) * 0.45, 0.0, 1.0));

    // ---- head rig about the neck ----------------------------------------
    vec3 pivot = vec3(uFaceX, uHeadY, 0.0);
    vec3 local = pos - pivot;
    float cy = cos(uYaw);
    float sy = sin(uYaw);
    local = vec3(local.x * cy + local.z * sy, local.y, -local.x * sy + local.z * cy);
    float cx = cos(uPitch);
    float sx = sin(uPitch);
    local = vec3(local.x, local.y * cx - local.z * sx, local.y * sx + local.z * cx);
    float cz = cos(uRoll);
    float sz = sin(uRoll);
    local = vec3(local.x * cz - local.y * sz, local.x * sz + local.y * cz, local.z);
    pos = mix(pos, pivot + local, head);

    // ---- lip sync --------------------------------------------------------
    // Ellipse on the front of the face only: jaw drops, mouth widens, and the
    // lower lip loses brightness so the opening reads as an actual gap.
    vec2 mouthUV = vec2((position.x - uFaceX) / 0.165, (position.y - uMouthY) / 0.105);
    float mouthQ = dot(mouthUV, mouthUV);
    float front = smoothstep(0.10, 0.36, position.z);
    float mouth = exp(-mouthQ * 2.1) * front * head;
    float open = clamp(uSpeech, 0.0, 1.2) * mouth;

    pos.y -= open * 0.20;
    pos.x += (position.x - uFaceX) * open * 0.28;
    pos.z += open * 0.03;

    float lowerLip = smoothstep(uMouthY + 0.02, uMouthY - 0.06, position.y);
    float gap = clamp(uSpeech, 0.0, 1.0) * exp(-mouthQ * 1.4) * lowerLip * front * head;

    // ---- scan formation --------------------------------------------------
    // The band forms everything below it; per-particle seed offsets keep the
    // edge ragged instead of a straight cut.
    float wob = (aSeed - 0.5) * 0.22;
    float formed = smoothstep(uBandY + 0.42 + wob, uBandY - 0.24 + wob, position.y);
    float airborne = mix(1.0, 1.0 - formed, uBandOn);
    float dispersion = clamp(uScatter, 0.0, 1.0) * airborne;

    float gate = smoothstep(aSeed * 0.5, 0.5 + aSeed * 0.5, dispersion);
    pos += aScatter * gate * (1.0 + 0.6 * dispersion);

    float bandDist = abs(position.y - uBandY);
    float scanGlow = uBandStrength * exp(-bandDist * 11.0);
    float scanHalo = uBandStrength * exp(-bandDist * 2.0) * 0.22;

    // Airborne particles keep drifting so the cloud never freezes mid-flight.
    float fly = dispersion;
    vec3 wobble = vec3(
      sin(uTime * 0.9 + aPhase * 3.1 + pos.y * 2.2),
      sin(uTime * 1.13 + aPhase * 1.7 + pos.x * 2.4),
      sin(uTime * 0.71 + aPhase * 2.3 + pos.z * 2.0)
    );
    // A rigid-body rig alone reads as frozen once the bust is a particle field:
    // neighbouring dots are dense enough that a few pixels of shift is invisible.
    // The per-particle wander and slow twinkle are what make it look alive.
    pos += wobble * mix(0.028, 0.05, fly) * uTurbo;

    vec3 tinted = mix(aColor, aColor * vec3(0.60, 0.84, 1.0), fly * 0.6);
    vec3 glow = vec3(0.55, 0.88, 1.0) * (scanGlow * 0.95 + scanHalo);
    vColor = min(vec3(1.0), tinted * uBrightness * (1.0 + 0.35 * fly) + glow);
    vAlpha = aAlpha * (1.0 - 0.55 * gap) * (1.0 - 0.12 * fly);
    // Slow per-particle twinkle: keeps the surface from reading as a static
    // decal without turning into noise (period ~5-9s, amplitude ~12%).
    vAlpha *= 0.88 + 0.12 * sin(uTime * 1.1 + aPhase * 6.283);

    vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
    float sizeBoost = 1.0 + 0.55 * fly + 0.55 * scanGlow;
    gl_PointSize = clamp(uSize * aScale * uPixelRatio * sizeBoost, 1.0, 9.0 * uPixelRatio);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const FRAGMENT_SHADER = `
  uniform sampler2D uSprite;
  uniform float uOpacity;

  varying vec3 vColor;
  varying float vAlpha;

  void main() {
    vec4 sprite = texture2D(uSprite, gl_PointCoord);
    float alpha = sprite.a * vAlpha * uOpacity;
    // Discard only truly invisible fragments: a higher cut-off clips the
    // sprite's soft skirt at low opacity, which turns dim particles into hard
    // dots and makes the whole bust read as confetti.
    if (alpha <= 0.0) discard;
    gl_FragColor = vec4(vColor, alpha);
  }
`;

function createParticleTexture(): THREE.CanvasTexture {
  // Soft round sprite: a single sample must stay well below white so dense
  // filaments accumulate into luminous mid-tones instead of blowing out. The
  // reference portrait has 0.2% clipped pixels; a hard disc clipped 3.5%.
  const canvas = document.createElement('canvas');
  canvas.width = 32;
  canvas.height = 32;
  const ctx = canvas.getContext('2d');
  if (ctx) {
    const gradient = ctx.createRadialGradient(16, 16, 0, 16, 16, 16);
    gradient.addColorStop(0, 'rgba(255,255,255,0.42)');
    gradient.addColorStop(0.4, 'rgba(255,255,255,0.26)');
    gradient.addColorStop(0.72, 'rgba(255,255,255,0.09)');
    gradient.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 32, 32);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  return texture;
}

function fitScale(cloud: AvatarCloud, aspect: number, framing: 'panel' | 'preview'): number {
  const visibleHeight = 2 * CAMERA_Z * Math.tan((CAMERA_FOV * Math.PI) / 360);
  const visibleWidth = visibleHeight * aspect;
  const width = Math.max(0.001, cloud.max[0] - cloud.min[0]);
  const height = Math.max(0.001, cloud.max[1] - cloud.min[1]);
  const margin = framing === 'preview' ? 1.05 : PANEL_FIT_MARGIN;
  return Math.min(visibleWidth / (width * margin), visibleHeight / (height * margin));
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

/** Face rig uniforms derived from each baked bust (mouth + neck pivot). */
function faceUniforms(cloud: AvatarCloud): Record<string, { value: number }> {
  const anchors = computeFaceAnchors(cloud);
  return {
    uFaceX: { value: anchors.x },
    uHeadY: { value: anchors.headY },
    uMouthY: { value: anchors.mouthY },
  };
}

interface RigUniforms {
  uYaw: { value: number };
  uPitch: { value: number };
  uRoll: { value: number };
  uBreath: { value: number };
  uSway: { value: number };
}

function circlePoints(radius: number, segments: number, from = 0, to = TAU): THREE.Vector3[] {
  const points: THREE.Vector3[] = [];
  for (let i = 0; i <= segments; i += 1) {
    const angle = from + ((to - from) * i) / segments;
    points.push(new THREE.Vector3(Math.cos(angle) * radius, Math.sin(angle) * radius, 0));
  }
  return points;
}

export const ThreeHologram: React.FC<ThreeHologramProps> = ({ appearance, framing = 'panel', state = 'idle' }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const appearanceRef = useRef(appearance);
  const framingRef = useRef(framing);
  const stateRef = useRef(state);

  useEffect(() => {
    appearanceRef.current = appearance;
  }, [appearance]);

  useEffect(() => {
    framingRef.current = framing;
  }, [framing]);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const width = container.clientWidth || 320;
    const height = container.clientHeight || 320;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(CAMERA_FOV, width / height, 0.1, 100);
    camera.position.set(0, 0.04, CAMERA_Z);
    camera.lookAt(0, 0.04, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    container.appendChild(renderer.domElement);

    const group = new THREE.Group();
    scene.add(group);

    const particleTexture = createParticleTexture();

    let clouds: Record<CharacterAppearance, AvatarCloud> | null = null;
    let activeAppearance = appearanceRef.current;
    let points: THREE.Points<THREE.BufferGeometry, THREE.ShaderMaterial> | null = null;
    let bloomPoints: THREE.Points<THREE.BufferGeometry, THREE.ShaderMaterial> | null = null;
    let bloomMaterial: THREE.ShaderMaterial | null = null;
    let disposed = false;

    const positions = new Float32Array(CAPACITY * 3);
    const colors = new Float32Array(CAPACITY * 3);
    const scatter = new Float32Array(CAPACITY * 3);
    const alphas = new Float32Array(CAPACITY);
    const scales = new Float32Array(CAPACITY);
    const phases = new Float32Array(CAPACITY);
    const seeds = new Float32Array(CAPACITY);

    const attributeRand = mulberry32(0x9e3779b9);
    for (let i = 0; i < CAPACITY; i += 1) {
      scales[i] = 0.72 + attributeRand() * 0.72;
      phases[i] = attributeRand() * TAU;
      seeds[i] = attributeRand();
    }

    let stage: Stage = 'reveal';
    let stageStart = 0;
    let pendingAppearance: CharacterAppearance | null = null;

    const applyFraming = () => {
      if (!clouds) return;
      const cloud = clouds[appearanceRef.current];
      const aspect = (container.clientWidth || width) / (container.clientHeight || height);
      const scale = fitScale(cloud, aspect, framingRef.current);
      group.scale.setScalar(scale);
      const lift = framingRef.current === 'preview' ? 0 : PANEL_LIFT;
      group.position.set(
        -((cloud.min[0] + cloud.max[0]) / 2) * scale,
        -((cloud.min[1] + cloud.max[1]) / 2) * scale + lift,
        0,
      );
    };

    const applyStyle = () => {
      if (!points) return;
      const style = RENDER_STYLE[activeAppearance];
      points.material.uniforms.uSize.value = style.size;
      points.material.uniforms.uOpacity.value = style.opacity * (framingRef.current === 'preview' ? 1.1 : 1);
      if (bloomMaterial) {
        bloomMaterial.uniforms.uSize.value = style.size * 3.4;
        bloomMaterial.uniforms.uOpacity.value = 0.03 * (framingRef.current === 'preview' ? 1.1 : 1);
      }
    };

    // ---- reference HUD rings -------------------------------------------
    // Every storyboard cell carries two thin concentric rings plus tick marks.
    // They are part of the character's look, not decoration, so they ship with
    // the bust and follow its fitted size.
    const ringGroup = new THREE.Group();
    group.add(ringGroup);
    const ringMaterials: THREE.Material[] = [];

    const addRing = (pointsList: THREE.Vector3[], color: number, opacity: number, closed = true) => {
      const geometry = new THREE.BufferGeometry().setFromPoints(pointsList);
      const material = new THREE.LineBasicMaterial({
        color,
        transparent: true,
        opacity,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      ringMaterials.push(material);
      const line = closed ? new THREE.LineLoop(geometry, material) : new THREE.Line(geometry, material);
      ringGroup.add(line);
      return line;
    };

    let sweepArc: THREE.Line | null = null;

    const buildRings = (cloud: AvatarCloud) => {
      while (ringGroup.children.length) {
        const child = ringGroup.children.pop() as THREE.Line;
        child.geometry.dispose();
      }
      for (const material of ringMaterials) material.dispose();
      ringMaterials.length = 0;

      const cloudWidth = cloud.max[0] - cloud.min[0];
      const cloudHeight = cloud.max[1] - cloud.min[1];
      const cx = (cloud.min[0] + cloud.max[0]) / 2;
      const cy = (cloud.min[1] + cloud.max[1]) / 2 + 0.05;
      const radius = Math.max(cloudWidth, cloudHeight) * 0.66;

      ringGroup.position.set(cx, cy, -0.75);

      addRing(circlePoints(radius, 180), 0x1b6b82, 0.34);
      addRing(circlePoints(radius * 1.18, 180), 0x144c60, 0.16);

      // Dashed inner ring, matching the ticked ring in the storyboard cells.
      const dashGeometry = new THREE.BufferGeometry().setFromPoints(circlePoints(radius * 0.93, 220));
      const dashMaterial = new THREE.LineDashedMaterial({
        color: 0x2a8fa8,
        transparent: true,
        opacity: 0.42,
        dashSize: 0.06,
        gapSize: 0.11,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      ringMaterials.push(dashMaterial);
      const dashLine = new THREE.Line(dashGeometry, dashMaterial);
      dashLine.computeLineDistances();
      ringGroup.add(dashLine);

      // Radial ticks.
      const tickPoints: THREE.Vector3[] = [];
      const ticks = 96;
      for (let i = 0; i < ticks; i += 1) {
        const angle = (TAU * i) / ticks;
        const inner = radius * 1.005;
        const outer = radius * (i % 8 === 0 ? 1.045 : 1.022);
        tickPoints.push(new THREE.Vector3(Math.cos(angle) * inner, Math.sin(angle) * inner, 0));
        tickPoints.push(new THREE.Vector3(Math.cos(angle) * outer, Math.sin(angle) * outer, 0));
      }
      const tickGeometry = new THREE.BufferGeometry().setFromPoints(tickPoints);
      const tickMaterial = new THREE.LineBasicMaterial({
        color: 0x2f93ad,
        transparent: true,
        opacity: 0.4,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      ringMaterials.push(tickMaterial);
      ringGroup.add(new THREE.LineSegments(tickGeometry, tickMaterial));

      // Bright arc that slowly sweeps around the ring.
      sweepArc = addRing(circlePoints(radius * 1.01, 48, -0.5, 0.5), 0x8beeff, 0.55, false);
    };

    const swapCloud = (cloud: AvatarCloud) => {
      // Typed-array `set` throws on overflow and the caller is inside a promise
      // chain, so an out-of-date bake used to fail silently with a blank bust.
      if (cloud.count > CAPACITY) {
        console.error(
          `[Hologram] cloud has ${cloud.count} particles but CAPACITY is ${CAPACITY}; raise CAPACITY or re-bake.`,
        );
        return;
      }
      positions.set(cloud.positions);
      colors.set(cloud.colors);
      scatter.set(cloud.scatter);
      for (let i = 0; i < CAPACITY; i += 1) alphas[i] = i < cloud.count ? 1 : 0;
      if (!points) return;
      const attributes = points.geometry.attributes;
      attributes.position.needsUpdate = true;
      attributes.aColor.needsUpdate = true;
      attributes.aScatter.needsUpdate = true;
      attributes.aAlpha.needsUpdate = true;
      Object.assign(points.material.uniforms, faceUniforms(cloud));
      buildRings(cloud);
    };

    Promise.all([
      fetch(CLOUD_URLS.male).then((response) => (response.ok ? response.arrayBuffer() : Promise.reject(new Error('male cloud missing')))),
      fetch(CLOUD_URLS.female).then((response) => (response.ok ? response.arrayBuffer() : Promise.reject(new Error('female cloud missing')))),
    ])
      .then(([maleBuffer, femaleBuffer]) => {
        if (disposed) return;

        clouds = {
          male: buildCloud(new Float32Array(maleBuffer), 0x51ed270b),
          female: buildCloud(new Float32Array(femaleBuffer), 0x2545f491),
        };

        const active = clouds[appearanceRef.current];
        activeAppearance = appearanceRef.current;

        if (active.count > CAPACITY) {
          console.error(
            `[Hologram] cloud has ${active.count} particles but CAPACITY is ${CAPACITY}; raise CAPACITY or re-bake.`,
          );
          return;
        }

        positions.set(active.positions);
        colors.set(active.colors);
        scatter.set(active.scatter);
        for (let i = 0; i < CAPACITY; i += 1) alphas[i] = i < active.count ? 1 : 0;

        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geometry.setAttribute('aColor', new THREE.BufferAttribute(colors, 3));
        geometry.setAttribute('aScatter', new THREE.BufferAttribute(scatter, 3));
        geometry.setAttribute('aAlpha', new THREE.BufferAttribute(alphas, 1));
        geometry.setAttribute('aScale', new THREE.BufferAttribute(scales, 1));
        geometry.setAttribute('aPhase', new THREE.BufferAttribute(phases, 1));
        geometry.setAttribute('aSeed', new THREE.BufferAttribute(seeds, 1));

        const rig: RigUniforms = {
          uYaw: { value: 0 },
          uPitch: { value: 0 },
          uRoll: { value: 0 },
          uBreath: { value: 0 },
          uSway: { value: 0 },
        };

        const material = new THREE.ShaderMaterial({
          uniforms: {
            uSprite: { value: particleTexture },
            uSize: { value: RENDER_STYLE[appearanceRef.current].size },
            uPixelRatio: { value: Math.min(window.devicePixelRatio, 2) },
            uOpacity: {
              value: RENDER_STYLE[appearanceRef.current].opacity * (framingRef.current === 'preview' ? 1.1 : 1),
            },
            uTime: { value: 0 },
            uScatter: { value: 1 },
            uTurbo: { value: 1 },
            uBrightness: { value: 1 },
            uSpeech: { value: 0 },
            uBandY: { value: -2.5 },
            uBandStrength: { value: 0 },
            uBandOn: { value: reducedMotion ? 0 : 1 },
            ...rig,
            ...faceUniforms(active),
          },
          transparent: true,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
          vertexShader: VERTEX_SHADER,
          fragmentShader: FRAGMENT_SHADER,
        });

        points = new THREE.Points(geometry, material);
        group.add(points);

        // Cheap two-pass bloom: the reference portrait glows into the card, and a
        // single sprite pass with the same geometry is enough to fake it without
        // an EffectComposer dependency.
        bloomMaterial = new THREE.ShaderMaterial({
          uniforms: { ...material.uniforms },
          transparent: true,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
          vertexShader: VERTEX_SHADER,
          fragmentShader: FRAGMENT_SHADER,
        });
        for (const key of Object.keys(bloomMaterial.uniforms)) {
          bloomMaterial.uniforms[key] = { value: material.uniforms[key].value };
        }
        bloomMaterial.uniforms.uSize.value = RENDER_STYLE[appearanceRef.current].size * 3.4;
        bloomMaterial.uniforms.uOpacity.value = 0.03;
        bloomPoints = new THREE.Points(geometry, bloomMaterial);
        group.add(bloomPoints);

        applyFraming();
        buildRings(active);

        stage = reducedMotion ? 'idle' : 'reveal';
        stageStart = elapsed;
      })
      .catch((error) => {
        console.warn('[Hologram] avatar cloud unavailable:', error);
      });

    // Ambient cybernetic embers.
    const emberCount = 90;
    const emberPositions = new Float32Array(emberCount * 3);
    const emberColors = new Float32Array(emberCount * 3);
    for (let i = 0; i < emberCount; i += 1) {
      const angle = Math.random() * TAU;
      const radius = 0.6 + Math.random() * 1.3;
      emberPositions[i * 3] = Math.cos(angle) * radius;
      emberPositions[i * 3 + 1] = (Math.random() - 0.5) * 1.7 + 0.1;
      emberPositions[i * 3 + 2] = (Math.random() - 0.5) * 0.8;
      const white = Math.random() > 0.8;
      emberColors[i * 3] = white ? 1 : 0.08;
      emberColors[i * 3 + 1] = white ? 1 : 0.85;
      emberColors[i * 3 + 2] = white ? 1 : 1;
    }
    const emberGeometry = new THREE.BufferGeometry();
    emberGeometry.setAttribute('position', new THREE.BufferAttribute(emberPositions, 3));
    emberGeometry.setAttribute('color', new THREE.BufferAttribute(emberColors, 3));
    const emberMaterial = new THREE.PointsMaterial({
      size: 0.026,
      vertexColors: true,
      map: particleTexture,
      transparent: true,
      opacity: 0.45,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const embers = new THREE.Points(emberGeometry, emberMaterial);
    group.add(embers);

    let frame = 0;
    const clock = new THREE.Clock();
    let elapsed = 0;

    // Real gateway audio levels drive the jaw; the envelope owns smoothing.
    const speech = new SpeechEnvelope();
    let audioClock = 0;
    const unsubscribeAudio = backendBridge.onAudioLevel((level) => {
      speech.noteAudioLevel(level, audioClock);
    });

    // Head follows the pointer: the cheapest, strongest "this thing is alive"
    // cue in the whole scene, so it is always on outside reduced motion.
    const look = { x: 0, y: 0, targetX: 0, targetY: 0 };
    const handlePointer = (event: PointerEvent) => {
      const rect = container.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      look.targetX = clamp((event.clientX - (rect.left + rect.width / 2)) / (rect.width * 0.85), -1, 1);
      look.targetY = clamp((event.clientY - (rect.top + rect.height / 2)) / (rect.height * 0.85), -1, 1);
    };
    if (!reducedMotion) window.addEventListener('pointermove', handlePointer, { passive: true });

    const animate = () => {
      frame = requestAnimationFrame(animate);
      const delta = Math.min(clock.getDelta(), 0.1);
      elapsed += delta;
      audioClock = elapsed;

      const debug = hologramDebug.enabled ? hologramDebug : null;
      const paused = Boolean(debug?.paused);

      look.x += (look.targetX - look.x) * (1 - Math.exp(-delta * 5.5));
      look.y += (look.targetY - look.y) * (1 - Math.exp(-delta * 5.5));

      if (points && clouds && !paused) {
        if (appearanceRef.current !== activeAppearance && stage !== 'dissolve') {
          pendingAppearance = appearanceRef.current;
          stage = 'dissolve';
          stageStart = elapsed;
        }
        if (stage === 'dissolve') {
          const dissolve = sampleDissolve(elapsed - stageStart);
          if (dissolve.progress >= 1 && pendingAppearance) {
            // Swap at peak scatter: the character changes while nothing is
            // formed, then the scan rebuilds the new bust from the bottom up.
            activeAppearance = pendingAppearance;
            pendingAppearance = null;
            swapCloud(clouds[activeAppearance]);
            applyFraming();
            applyStyle();
            stage = 'reveal';
            stageStart = elapsed;
          }
        } else if (stage === 'reveal' && elapsed - stageStart >= REVEAL_SECONDS) {
          stage = 'idle';
        }
      }

      if (points) {
        const uniforms = points.material.uniforms;

        if (reducedMotion) {
          uniforms.uTime.value = 0;
          uniforms.uScatter.value = 0;
          uniforms.uTurbo.value = 0;
          uniforms.uBrightness.value = 1;
          uniforms.uSpeech.value = 0;
          uniforms.uBandOn.value = 0;
          uniforms.uBandY.value = BAND_END_Y;
          uniforms.uBandStrength.value = 0;
          uniforms.uYaw.value = 0;
          uniforms.uPitch.value = 0;
          uniforms.uRoll.value = 0;
          uniforms.uBreath.value = 0;
          uniforms.uSway.value = 0;
        } else {
          // Debug pause freezes the rig *and* rewinds the reveal, so captures are
          // byte-stable at a chosen moment.
          const rigTime = paused && debug ? debug.time : elapsed;
          const revealSeconds =
            paused && debug
              ? debug.time
              : stage === 'dissolve'
                ? 0
                : stage === 'reveal'
                  ? elapsed - stageStart
                  : REVEAL_SECONDS;

          const sample =
            stage === 'dissolve' && !paused
              ? { ...sampleHologramTimeline(REVEAL_SECONDS, stateRef.current), ...sampleDissolve(elapsed - stageStart) }
              : sampleHologramTimeline(revealSeconds, stateRef.current);

          const forcedDispersion = debug?.dispersion ?? null;
          uniforms.uScatter.value = forcedDispersion ?? sample.scatter;
          uniforms.uTurbo.value = (debug?.turbulence ?? 1) * sample.turbulence;
          uniforms.uBrightness.value = (debug?.brightness ?? 1) * sample.brightness;
          uniforms.uBandOn.value = forcedDispersion !== null ? 0 : sample.bandActive ? 1 : 0;
          uniforms.uBandY.value = sample.bandY;
          uniforms.uBandStrength.value = sample.bandStrength;
          uniforms.uTime.value = rigTime;

          if (hologramDebug.enabled) {
            (
              window as unknown as {
                __jarvisStage?: {
                  stage: string;
                  appearance: string;
                  scatter: number;
                  reveal: number;
                  clock: number;
                };
              }
            ).__jarvisStage = {
              stage,
              appearance: activeAppearance,
              scatter: sample.scatter,
              reveal: Math.round(revealSeconds * 100) / 100,
              clock: Math.round(elapsed * 100) / 100,
            };
          }

          const speechLevel = speech.update(delta, elapsed, stateRef.current === 'speaking');
          uniforms.uSpeech.value = Math.min(1, debug?.speech ?? speechLevel);

          // Layered idle motion: slow weight shift, breathing, head wander and
          // a pointer-follow glance. Speech adds a small nod on top.
          uniforms.uYaw.value =
            Math.sin(rigTime * 0.41) * 0.085 +
            Math.sin(rigTime * 0.17 + 1.1) * 0.040 +
            look.x * 0.16 +
            speechLevel * 0.02 * Math.sin(rigTime * 3.2);
          uniforms.uPitch.value =
            Math.sin(rigTime * 0.33 + 0.9) * 0.055 +
            look.y * 0.14 +
            speechLevel * 0.014 * Math.sin(rigTime * 11);
          uniforms.uRoll.value = Math.sin(rigTime * 0.27 + 2.2) * 0.024 - look.x * 0.03;
          uniforms.uBreath.value = 0.5 + 0.5 * Math.sin(rigTime * 0.95);
          uniforms.uSway.value = Math.sin(rigTime * 0.29 + 0.4) * 0.6 + look.x * 0.4;

          if (debug?.size != null) uniforms.uSize.value = debug.size;
          if (debug?.opacity != null) uniforms.uOpacity.value = debug.opacity;
          if (debug?.hud != null) {
            ringGroup.visible = debug.hud;
            embers.visible = debug.hud;
          }
        }
      }

      if (bloomMaterial && points) {
        const source = points.material.uniforms;
        for (const key of Object.keys(bloomMaterial.uniforms)) {
          if (key === 'uSize' || key === 'uOpacity' || key === 'uSprite') continue;
          bloomMaterial.uniforms[key].value = source[key].value;
        }
      }

      if (!reducedMotion) {
        embers.rotation.y = Math.sin(elapsed * 0.12) * 0.08;
        if (sweepArc) sweepArc.rotation.z = elapsed * 0.18;
      }

      renderer.render(scene, camera);

      // One-shot framebuffer dump for capture tooling. `toDataURL` returns an
      // empty image for very dim additive frames (Chromium's unpremultiply path
      // gives up), so read the raw RGBA buffer and let the tool flip/composite.
      if (hologramDebug.enabled && hologramDebug.capture) {
        hologramDebug.capture = false;
        const gl = renderer.getContext();
        const width = renderer.domElement.width;
        const height = renderer.domElement.height;
        const buffer = new Uint8Array(width * height * 4);
        gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, buffer);
        let binary = '';
        for (let index = 0; index < buffer.length; index += 0x8000) {
          binary += String.fromCharCode(...buffer.subarray(index, index + 0x8000));
        }
        (
          window as unknown as { __jarvisFrame?: { width: number; height: number; data: string } }
        ).__jarvisFrame = { width, height, data: btoa(binary) };
      }
    };

    animate();

    const handleResize = () => {
      const nextWidth = container.clientWidth;
      const nextHeight = container.clientHeight;
      if (!nextWidth || !nextHeight) return;
      camera.aspect = nextWidth / nextHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(nextWidth, nextHeight);
      applyFraming();
    };

    // Flex parents settle after mount; observe the box so the bust fits the
    // final card height instead of the pre-layout guess.
    const observer = new ResizeObserver(handleResize);
    observer.observe(container);

    return () => {
      disposed = true;
      observer.disconnect();
      unsubscribeAudio();
      window.removeEventListener('pointermove', handlePointer);
      cancelAnimationFrame(frame);

      if (points) {
        points.geometry.dispose();
        points.material.dispose();
      }
      if (bloomMaterial) bloomMaterial.dispose();
      bloomPoints = null;

      while (ringGroup.children.length) {
        const child = ringGroup.children.pop() as THREE.Line;
        child.geometry.dispose();
      }
      for (const material of ringMaterials) material.dispose();

      emberGeometry.dispose();
      emberMaterial.dispose();
      particleTexture.dispose();

      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
      renderer.dispose();
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full select-none overflow-hidden pointer-events-none"
      role="img"
      aria-label={`${appearance} holographic assistant avatar`}
    />
  );
};
