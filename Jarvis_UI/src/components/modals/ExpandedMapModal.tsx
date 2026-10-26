import React, { useRef, useEffect } from 'react';
import * as THREE from 'three';
import { X, Satellite, Radio, ShieldAlert } from 'lucide-react';
import { audioService } from '../../services/audioService';

interface ExpandedMapModalProps {
  onClose: () => void;
}

export const ExpandedMapModal: React.FC<ExpandedMapModalProps> = ({ onClose }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const width = container.clientWidth || 800;
    const height = container.clientHeight || 520;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.set(0, 0, 4.2);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    const globeGroup = new THREE.Group();
    scene.add(globeGroup);

    // High-density Earth wireframe & dots
    const radius = 1.6;
    const wireGeo = new THREE.SphereGeometry(radius, 40, 40);
    const wireMat = new THREE.MeshBasicMaterial({
      color: 0x00f0ff,
      wireframe: true,
      transparent: true,
      opacity: 0.18,
    });
    const wireGlobe = new THREE.Mesh(wireGeo, wireMat);
    globeGroup.add(wireGlobe);

    // Multiple concentric orbital rings
    [1.9, 2.15, 2.4].forEach((r, idx) => {
      const ringGeo = new THREE.RingGeometry(r, r + 0.015, 64);
      const ringMat = new THREE.MeshBasicMaterial({
        color: idx === 1 ? 0xff2b44 : 0x00f0ff,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.35,
      });
      const ring = new THREE.Mesh(ringGeo, ringMat);
      ring.rotation.x = Math.PI / (2.2 + idx * 0.4);
      ring.rotation.y = Math.PI / (3 + idx);
      globeGroup.add(ring);
    });

    let frameId: number;
    let clock = new THREE.Clock();

    const animate = () => {
      frameId = requestAnimationFrame(animate);
      const elapsed = clock.getElapsedTime();
      globeGroup.rotation.y = elapsed * 0.18;
      globeGroup.rotation.x = Math.sin(elapsed * 0.1) * 0.1;
      renderer.render(scene, camera);
    };

    animate();

    const handleResize = () => {
      if (!container) return;
      camera.aspect = container.clientWidth / container.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, container.clientHeight);
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(frameId);
      if (container && renderer.domElement) {
        container.removeChild(renderer.domElement);
      }
      wireGeo.dispose();
      wireMat.dispose();
      renderer.dispose();
    };
  }, []);

  return (
    <div className="w-[880px] max-w-[95vw] h-[640px] max-h-[90vh] bg-[#050b16] border border-cyan-500/60 rounded-xl shadow-[0_0_50px_rgba(0,240,255,0.3)] flex flex-col overflow-hidden">
      {/* Top Header */}
      <div className="h-11 px-4 border-b border-cyan-500/30 flex items-center justify-between bg-[#040812] select-none">
        <div className="flex items-center space-x-3">
          <Satellite className="w-5 h-5 text-cyan-400 animate-pulse" />
          <div>
            <h3 className="text-sm font-bold text-slate-100 tracking-wider uppercase">
              SAT-LINK ORBITAL COMMAND CENTER — TACTICAL GEOMESH
            </h3>
            <p className="text-[10px] text-cyan-400/80 font-mono">
              Constellation: GEO-38 • Altitude: 35,786 km • Low-Latency Telemetry Active
            </p>
          </div>
        </div>

        <button
          onClick={() => { audioService.playClick(); onClose(); }}
          className="text-slate-400 hover:text-cyan-300 p-1"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Main Tactical Visualizer */}
      <div className="flex-1 relative overflow-hidden grid grid-cols-12">
        <div ref={containerRef} className="col-span-8 h-full relative cursor-grab active:cursor-grabbing" />

        {/* Right Telemetry Telemetry Sidebar */}
        <div className="col-span-4 h-full border-l border-cyan-500/20 bg-[#040712] p-4 flex flex-col justify-between text-xs font-mono">
          <div className="space-y-4">
            <div className="flex items-center space-x-2 text-cyan-400 border-b border-cyan-500/20 pb-2">
              <Radio className="w-4 h-4" />
              <span className="font-bold tracking-wider">LIVE TELEMETRY STREAM</span>
            </div>

            <div className="space-y-2 text-[11px] text-slate-300">
              <div className="flex justify-between">
                <span className="text-slate-500">Subsolar Point:</span>
                <span className="text-cyan-300">11.84° N, 78.42° E</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Orbital Velocity:</span>
                <span className="text-cyan-300">3.07 km/s</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Doppler Shift:</span>
                <span className="text-emerald-400">+1.24 kHz (Locked)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Signal-to-Noise:</span>
                <span className="text-emerald-400">28.4 dB</span>
              </div>
            </div>

            <div className="border border-red-500/30 bg-red-950/20 rounded p-2.5 space-y-1.5">
              <div className="flex items-center space-x-1.5 text-red-400 font-bold text-[10px]">
                <ShieldAlert className="w-3.5 h-3.5" />
                <span>ACTIVE ANOMALY DETECTED</span>
              </div>
              <p className="text-[10px] text-slate-300 font-sans leading-tight">
                Sector 04 electromagnetic deviation recorded. Automatic triangulation protocol initiated.
              </p>
            </div>
          </div>

          <div className="pt-3 border-t border-cyan-500/20 flex justify-end">
            <button
              onClick={() => { audioService.playClick(); onClose(); }}
              className="px-4 py-1.5 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold rounded text-xs transition-colors"
            >
              Close Tactical View
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
