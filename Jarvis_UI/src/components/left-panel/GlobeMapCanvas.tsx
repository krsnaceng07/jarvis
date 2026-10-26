import React, { useRef, useEffect } from 'react';
import * as THREE from 'three';
import { Bell, MapPin, MoreHorizontal, PlusCircle, Search } from 'lucide-react';
import { audioService } from '../../services/audioService';

interface GlobeMapCanvasProps {
  is3D: boolean;
  activeNav: string;
  onNavChange: (nav: string) => void;
  onSelectEvent?: (eventInfo: string) => void;
}

// Equirectangular heat blobs layered over the NASA night-lights texture.
const HEAT_SPOTS = [
  { lat: 30, lng: 78, radius: 62, strength: 0.62 },
  { lat: 38, lng: 46, radius: 46, strength: 0.55 },
  { lat: 12, lng: 18, radius: 40, strength: 0.34 },
  { lat: 52, lng: 24, radius: 34, strength: 0.3 },
  { lat: 36, lng: 128, radius: 40, strength: 0.42 },
];

const BEACONS = [
  { lat: 51, lng: -1, tone: 'amber' },
  { lat: 40, lng: -74, tone: 'amber' },
  { lat: 30, lng: 31, tone: 'red' },
  { lat: 19, lng: 73, tone: 'amber' },
  { lat: 35, lng: 51, tone: 'red' },
  { lat: 35, lng: 105, tone: 'amber' },
  { lat: 36, lng: 138, tone: 'amber' },
  { lat: -1, lng: 37, tone: 'amber' },
  { lat: -23, lng: 18, tone: 'red' },
  { lat: 48, lng: 30, tone: 'red' },
] as const;

function buildHeatTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = 1024;
  canvas.height = 512;
  const ctx = canvas.getContext('2d');
  if (ctx) {
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, 1024, 512);
    for (const spot of HEAT_SPOTS) {
      const x = ((spot.lng + 180) / 360) * 1024;
      const y = ((90 - spot.lat) / 180) * 512;
      const gradient = ctx.createRadialGradient(x, y, 0, x, y, spot.radius);
      gradient.addColorStop(0, `rgba(255, 46, 66, ${spot.strength})`);
      gradient.addColorStop(0.45, `rgba(255, 60, 40, ${spot.strength * 0.55})`);
      gradient.addColorStop(1, 'rgba(255, 40, 30, 0)');
      ctx.fillStyle = gradient;
      ctx.fillRect(x - spot.radius, y - spot.radius, spot.radius * 2, spot.radius * 2);
    }
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

export const GlobeMapCanvas: React.FC<GlobeMapCanvasProps> = ({
  is3D,
  activeNav,
  onNavChange,
  onSelectEvent,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const is3DRef = useRef(is3D);

  useEffect(() => {
    is3DRef.current = is3D;
  }, [is3D]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const width = container.clientWidth || 260;
    const height = container.clientHeight || 270;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 100);
    // Pulled back so the globe fills ~90% of the panel width like the reference
    // instead of bleeding past the left and right rail edges.
    camera.position.set(0, 0, 4.45);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    const mapGroup = new THREE.Group();
    scene.add(mapGroup);

    // Orient the globe over South Asia, matching the reference framing.
    mapGroup.rotation.y = -Math.PI * 0.45;
    mapGroup.rotation.x = 0.12;

    const radius = 1.22;

    // 1. Dark satellite Earth (NASA Blue Marble derivative shipped in /public).
    const baseSphereGeo = new THREE.SphereGeometry(radius, 64, 48);
    const baseSphereMat = new THREE.MeshBasicMaterial({
      color: 0x6d9dbb,
      transparent: true,
    });
    const baseSphere = new THREE.Mesh(baseSphereGeo, baseSphereMat);
    mapGroup.add(baseSphere);

    const loader = new THREE.TextureLoader();
    let earthTexture: THREE.Texture | null = null;
    loader.load('/textures/earth_blue_marble.jpg', (texture) => {
      texture.colorSpace = THREE.SRGBColorSpace;
      earthTexture = texture;
      baseSphereMat.map = texture;
      // Dim the daylight marble into the HUD's deep blue without losing continents.
      baseSphereMat.color.setHex(0x6478b8);
      baseSphereMat.needsUpdate = true;
    });

    // 2. Red telemetry heat zones.
    const heatTexture = buildHeatTexture();
    const heatGeo = new THREE.SphereGeometry(radius * 1.004, 64, 48);
    const heatMat = new THREE.MeshBasicMaterial({
      map: heatTexture,
      transparent: true,
      opacity: 0.55,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const heatSphere = new THREE.Mesh(heatGeo, heatMat);
    mapGroup.add(heatSphere);

    // 3. Fresnel atmosphere rim.
    const atmosphereGeo = new THREE.SphereGeometry(radius * 1.045, 48, 32);
    const atmosphereMat = new THREE.ShaderMaterial({
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      uniforms: { uColor: { value: new THREE.Color(0x2fa9d6) } },
      vertexShader: `
        varying vec3 vNormal;
        varying vec3 vView;
        void main() {
         vec4 mv = modelViewMatrix * vec4(position, 1.0);
          vNormal = normalize(normalMatrix * normal);
          vView = normalize(-mv.xyz);
          gl_Position = projectionMatrix * mv;
        }
      `,
      fragmentShader: `
        uniform vec3 uColor;
        varying vec3 vNormal;
        varying vec3 vView;
        void main() {
          float rim = pow(1.0 - abs(dot(vNormal, vView)), 2.6);
          gl_FragColor = vec4(uColor, rim * 0.42);
        }
      `,
    });
    const atmosphere = new THREE.Mesh(atmosphereGeo, atmosphereMat);
    mapGroup.add(atmosphere);

    // 4. Hotspot beacons.
    const ringGeo = new THREE.RingGeometry(0.050, 0.074, 32);
    const beaconMat = new THREE.MeshBasicMaterial({
      color: 0xf59e0b,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.85,
    });
    const redBeaconMat = new THREE.MeshBasicMaterial({
      color: 0xff2b44,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.85,
    });
    const beacons = BEACONS.map(({ lat, lng, tone }, index) => {
      const phi = (90 - lat) * (Math.PI / 180);
      const theta = (lng + 180) * (Math.PI / 180);
      const position = new THREE.Vector3(
        -(radius * Math.sin(phi) * Math.cos(theta)),
        radius * Math.cos(phi),
        radius * Math.sin(phi) * Math.sin(theta),
      );
      const normal = position.clone().normalize();
      const ring = new THREE.Mesh(ringGeo, tone === 'red' ? redBeaconMat : beaconMat);
      ring.position.copy(normal.clone().multiplyScalar(radius + 0.018));
      ring.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
      mapGroup.add(ring);
      return { ring, phase: index * 0.53 };
    });

    // 5. Satellite orbital arc.
    const orbitCurve = new THREE.EllipseCurve(0, 0, 1.5, 1.5, 0, 2 * Math.PI, false, 0);
    const orbitPoints = orbitCurve.getPoints(64);
    const orbitGeo = new THREE.BufferGeometry().setFromPoints(
      orbitPoints.map((p) => new THREE.Vector3(p.x, p.y * 0.4, p.y * 0.9)),
    );
    const orbitMat = new THREE.LineBasicMaterial({
      color: 0x00f0ff,
      transparent: true,
      opacity: 0.12,
    });
    const orbitArc = new THREE.Line(orbitGeo, orbitMat);
    orbitArc.rotation.z = Math.PI / 4;
    mapGroup.add(orbitArc);

    let animationFrameId = 0;
    const clock = new THREE.Clock();

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      const elapsed = clock.getElapsedTime();

      if (is3DRef.current) {
        mapGroup.rotation.y = -Math.PI * 0.45 + Math.sin(elapsed * 0.16) * 0.22;
      }

      let pulseOpacity = 0.85;
      beacons.forEach(({ ring, phase }) => {
        const pulseScale = 1.0 + (Math.sin(elapsed * 4.0 + phase) + 1.0) * 0.28;
        ring.scale.set(pulseScale, pulseScale, 1);
        pulseOpacity = Math.min(pulseOpacity, Math.max(0.25, 1.0 - (pulseScale - 1.0) * 0.7));
      });
      beaconMat.opacity = pulseOpacity;
      redBeaconMat.opacity = pulseOpacity;

      renderer.render(scene, camera);
    };

    animate();

    const handleResize = () => {
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (!w || !h) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };

    // Flex parents settle after mount, so observe the box instead of only the
    // window; otherwise the globe renders into a stale, taller viewport.
    const observer = new ResizeObserver(handleResize);
    observer.observe(container);
    handleResize();

    return () => {
      observer.disconnect();
      cancelAnimationFrame(animationFrameId);
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
      baseSphereGeo.dispose();
      baseSphereMat.dispose();
      earthTexture?.dispose();
      heatGeo.dispose();
      heatMat.dispose();
      heatTexture.dispose();
      atmosphereGeo.dispose();
      atmosphereMat.dispose();
      ringGeo.dispose();
      beaconMat.dispose();
      redBeaconMat.dispose();
      orbitGeo.dispose();
      orbitMat.dispose();
      renderer.dispose();
    };
  }, []);

  const navItems = [
    { label: 'Today', icon: <PlusCircle className="h-3.5 w-3.5" /> },
    { label: 'Map', icon: <MapPin className="h-3.5 w-3.5" /> },
    { label: 'Search', icon: <Search className="h-3.5 w-3.5" /> },
    { label: 'Alerts', icon: <Bell className="h-3.5 w-3.5" /> },
    { label: 'More', icon: <MoreHorizontal className="h-3.5 w-3.5" /> },
  ];

  return (
    <div className="relative flex min-h-0 w-full flex-1 flex-col overflow-hidden bg-[#03080f]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_46%,rgba(0,110,160,0.16),transparent_62%)]" />

      <div
        ref={containerRef}
        className="relative min-h-0 w-full flex-1 cursor-grab active:cursor-grabbing"
        role="img"
        aria-label="Satellite globe with live telemetry heat zones"
      />

      <div className="pointer-events-none absolute bottom-[46px] right-2 z-10 text-right text-[8px] font-mono text-slate-600">
        NASA Blue Marble / Natural Earth
      </div>

      <div className="relative z-20 flex h-[42px] w-full shrink-0 select-none items-center justify-around overflow-hidden border-t border-[#18343c] bg-[#040a0f]/95 px-1">
        {navItems.map((item) => {
          const isActive = activeNav === item.label;
          return (
            <button
              key={item.label}
              onClick={() => {
                audioService.playClick();
                onNavChange(item.label);
                onSelectEvent?.(`SAT-LINK Filter: ${item.label} Mode Active`);
              }}
              className={`relative flex h-full min-w-0 flex-1 flex-col items-center justify-center gap-0.5 text-[9px] font-semibold tracking-wide uppercase transition-colors ${
                isActive ? 'text-cyan-200' : 'text-slate-500 hover:text-slate-200'
              }`}
            >
              {item.icon}
              <span>{item.label}</span>
              {isActive && <span className="absolute bottom-0 h-[2px] w-6 bg-cyan-300 shadow-[0_0_6px_#00f0ff]" />}
            </button>
          );
        })}
      </div>
    </div>
  );
};
