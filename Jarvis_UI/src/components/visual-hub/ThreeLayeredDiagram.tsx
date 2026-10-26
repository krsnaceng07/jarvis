import React, { useRef, useEffect } from 'react';
import * as THREE from 'three';
import { useVisualHub } from '../../state/visualHubStore';

export const ThreeLayeredDiagram: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const { activeModelType } = useVisualHub();
  const typeRef = useRef(activeModelType);

  useEffect(() => {
    typeRef.current = activeModelType;
  }, [activeModelType]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const width = container.clientWidth || 320;
    const height = container.clientHeight || 220;

    const scene = new THREE.Scene();
    
    // Isometric Perspective Camera (matching reference screenshot angle!)
    const camera = new THREE.PerspectiveCamera(36, width / height, 0.1, 1000);
    camera.position.set(4.6, 4.2, 4.6);
    camera.lookAt(0, 0.1, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    // Active object group
    let currentModelGroup = new THREE.Group();
    scene.add(currentModelGroup);

    // Common High-Fidelity HUD Materials
    const cyanLineMat = new THREE.LineBasicMaterial({ 
      color: 0x00f0ff, 
      transparent: true, 
      opacity: 0.85 
    });
    const brightCyanLineMat = new THREE.LineBasicMaterial({ 
      color: 0x70f8ff, 
      transparent: true, 
      opacity: 0.95 
    });
    const faintCyanLineMat = new THREE.LineBasicMaterial({ 
      color: 0x00f0ff, 
      transparent: true, 
      opacity: 0.35 
    });
    const greenLineMat = new THREE.LineBasicMaterial({ 
      color: 0x00ff88, 
      transparent: true, 
      opacity: 0.95 
    });
    const orangeLineMat = new THREE.LineBasicMaterial({ 
      color: 0xf59e0b, 
      transparent: true, 
      opacity: 0.9 
    });
    const redLineMat = new THREE.LineBasicMaterial({ 
      color: 0xff2b44, 
      transparent: true, 
      opacity: 0.9 
    });
    const cyanFillMat = new THREE.MeshBasicMaterial({ 
      color: 0x0284c7, 
      transparent: true, 
      opacity: 0.35, 
      side: THREE.DoubleSide 
    });
    const columnTopMat = new THREE.MeshBasicMaterial({ 
      color: 0x00f0ff, 
      transparent: true, 
      opacity: 0.9 
    });

    // Helper to build model based on activeModelType
    const buildModel = (modelType: string) => {
      scene.remove(currentModelGroup);
      currentModelGroup = new THREE.Group();

      if (modelType === 'blueprint') {
        // --- 1. SpaceX Starship Blueprint Schematic ---
        const bodyGeo = new THREE.CylinderGeometry(0.55, 0.55, 2.6, 24, 6, true);
        const bodyWire = new THREE.LineSegments(new THREE.EdgesGeometry(bodyGeo), cyanLineMat);
        currentModelGroup.add(bodyWire);

        const noseGeo = new THREE.ConeGeometry(0.55, 1.1, 24, 4, true);
        const noseWire = new THREE.LineSegments(new THREE.EdgesGeometry(noseGeo), cyanLineMat);
        noseWire.position.y = 1.85;
        currentModelGroup.add(noseWire);

        for (let i = 0; i < 3; i++) {
          const engGeo = new THREE.CylinderGeometry(0.12, 0.18, 0.35, 12, 2, true);
          const engWire = new THREE.LineSegments(new THREE.EdgesGeometry(engGeo), orangeLineMat);
          const angle = (i * Math.PI * 2) / 3;
          engWire.position.set(Math.cos(angle) * 0.25, -1.45, Math.sin(angle) * 0.25);
          currentModelGroup.add(engWire);
        }

        const flapGeo = new THREE.BoxGeometry(0.55, 0.22, 0.04);
        const flap1 = new THREE.LineSegments(new THREE.EdgesGeometry(flapGeo), cyanLineMat);
        flap1.position.set(0.62, 1.3, 0);
        currentModelGroup.add(flap1);
        const flap2 = new THREE.LineSegments(new THREE.EdgesGeometry(flapGeo), cyanLineMat);
        flap2.position.set(-0.62, 1.3, 0);
        currentModelGroup.add(flap2);

      } else if (modelType === 'blackhole') {
        // --- 2. Black Hole Gravitational Lensing ---
        const sphereGeo = new THREE.SphereGeometry(0.65, 32, 32);
        const sphereMat = new THREE.MeshBasicMaterial({ color: 0x000000 });
        const sphere = new THREE.Mesh(sphereGeo, sphereMat);
        currentModelGroup.add(sphere);

        for (let r = 0.85; r < 2.1; r += 0.14) {
          const diskRingGeo = new THREE.RingGeometry(r, r + 0.04, 48);
          const col = r < 1.3 ? orangeLineMat : cyanLineMat;
          const diskRing = new THREE.Mesh(diskRingGeo, col);
          diskRing.rotation.x = Math.PI / 2.3;
          currentModelGroup.add(diskRing);
        }

        const photonGeo = new THREE.RingGeometry(1.02, 1.04, 64);
        const photonMesh = new THREE.Mesh(photonGeo, brightCyanLineMat);
        photonMesh.rotation.y = Math.PI / 3;
        currentModelGroup.add(photonMesh);

      } else if (modelType === 'fusion') {
        // --- 3. Tokamak Fusion Reactor Torus ---
        const torusGeo = new THREE.TorusGeometry(1.1, 0.42, 16, 48);
        const torusWire = new THREE.LineSegments(new THREE.EdgesGeometry(torusGeo), cyanLineMat);
        currentModelGroup.add(torusWire);

        const plasmaGeo = new THREE.TorusGeometry(1.1, 0.18, 16, 48);
        const plasmaMat = new THREE.MeshBasicMaterial({ color: 0xff2b44, transparent: true, opacity: 0.7 });
        const plasmaMesh = new THREE.Mesh(plasmaGeo, plasmaMat);
        currentModelGroup.add(plasmaMesh);

        for (let c = 0; c < 8; c++) {
          const coilGeo = new THREE.RingGeometry(0.68, 0.70, 32);
          const coil = new THREE.Mesh(coilGeo, greenLineMat);
          const angle = (c * Math.PI * 2) / 8;
          coil.position.set(Math.cos(angle) * 1.1, 0, Math.sin(angle) * 1.1);
          coil.rotation.y = -angle;
          currentModelGroup.add(coil);
        }

      } else if (modelType === 'mars') {
        // --- 4. Crewed Mars Mission Trajectory ---
        const sunMesh = new THREE.Mesh(new THREE.SphereGeometry(0.28, 16, 16), orangeLineMat);
        currentModelGroup.add(sunMesh);

        const earthOrbit = new THREE.Mesh(new THREE.RingGeometry(0.95, 0.97, 64), cyanLineMat);
        earthOrbit.rotation.x = Math.PI / 2;
        currentModelGroup.add(earthOrbit);

        const earthMesh = new THREE.Mesh(new THREE.SphereGeometry(0.1, 12, 12), cyanLineMat);
        earthMesh.position.set(0.96, 0, 0);
        currentModelGroup.add(earthMesh);

        const marsOrbit = new THREE.Mesh(new THREE.RingGeometry(1.7, 1.72, 64), redLineMat);
        marsOrbit.rotation.x = Math.PI / 2;
        currentModelGroup.add(marsOrbit);

        const marsMesh = new THREE.Mesh(new THREE.SphereGeometry(0.08, 12, 12), redLineMat);
        marsMesh.position.set(-1.7, 0, 0);
        currentModelGroup.add(marsMesh);

        const transferCurve = new THREE.EllipseCurve(0, 0, 1.35, 1.15, 0, Math.PI, false, 0);
        const transferGeo = new THREE.BufferGeometry().setFromPoints(transferCurve.getPoints(50));
        const transferLine = new THREE.Line(transferGeo, greenLineMat);
        transferLine.rotation.x = Math.PI / 2;
        currentModelGroup.add(transferLine);

      } else {
        // --- DEFAULT: 3-TIER ISOMETRIC LAYERED ARCHITECTURAL SCHEMATIC (MATCHING REFERENCE EXACTLY!) ---
        const planeSize = 2.4;
        const halfSize = planeSize / 2;

        // LAYER 3 (BOTTOM PLANE, y = -0.65): Base Coordinate Grid & Corner Brackets
        const bottomY = -0.65;
        
        // Plane perimeter
        const bottomRectPoints = [
          new THREE.Vector3(-halfSize, bottomY, -halfSize),
          new THREE.Vector3(halfSize, bottomY, -halfSize),
          new THREE.Vector3(halfSize, bottomY, halfSize),
          new THREE.Vector3(-halfSize, bottomY, halfSize),
          new THREE.Vector3(-halfSize, bottomY, -halfSize),
        ];
        const bottomRectGeo = new THREE.BufferGeometry().setFromPoints(bottomRectPoints);
        currentModelGroup.add(new THREE.Line(bottomRectGeo, cyanLineMat));

        // Bottom interior grid lines
        for (let g = -halfSize + 0.3; g < halfSize; g += 0.3) {
          const gridLine1 = new THREE.Line(
            new THREE.BufferGeometry().setFromPoints([
              new THREE.Vector3(g, bottomY, -halfSize),
              new THREE.Vector3(g, bottomY, halfSize),
            ]),
            faintCyanLineMat
          );
          currentModelGroup.add(gridLine1);

          const gridLine2 = new THREE.Line(
            new THREE.BufferGeometry().setFromPoints([
              new THREE.Vector3(-halfSize, bottomY, g),
              new THREE.Vector3(halfSize, bottomY, g),
            ]),
            faintCyanLineMat
          );
          currentModelGroup.add(gridLine2);
        }

        // LAYER 2 (MIDDLE PLANE, y = 0.05): Area Flow Graph & Isometric Grid
        const midY = 0.05;

        // Middle perimeter
        const midRectPoints = [
          new THREE.Vector3(-halfSize, midY, -halfSize),
          new THREE.Vector3(halfSize, midY, -halfSize),
          new THREE.Vector3(halfSize, midY, halfSize),
          new THREE.Vector3(-halfSize, midY, halfSize),
          new THREE.Vector3(-halfSize, midY, -halfSize),
        ];
        const midRectGeo = new THREE.BufferGeometry().setFromPoints(midRectPoints);
        currentModelGroup.add(new THREE.Line(midRectGeo, cyanLineMat));

        // Middle translucent glass plane fill
        const midPlaneGeo = new THREE.PlaneGeometry(planeSize, planeSize);
        const midPlaneMesh = new THREE.Mesh(midPlaneGeo, cyanFillMat);
        midPlaneMesh.rotation.x = -Math.PI / 2;
        midPlaneMesh.position.y = midY;
        currentModelGroup.add(midPlaneMesh);

        // Continuous Flowing Wave Graph on Middle Layer
        const wavePoints: THREE.Vector3[] = [];
        for (let x = -halfSize + 0.15; x <= halfSize - 0.15; x += 0.12) {
          const t = (x + halfSize) / planeSize;
          const y = midY + 0.02 + Math.sin(t * Math.PI * 3.5) * 0.16;
          const z = -0.3 + Math.cos(t * Math.PI * 2) * 0.45;
          wavePoints.push(new THREE.Vector3(x, y, z));
        }
        const waveGeo = new THREE.BufferGeometry().setFromPoints(wavePoints);
        const waveLine = new THREE.Line(waveGeo, greenLineMat);
        currentModelGroup.add(waveLine);

        // LAYER 1 (TOP PLANE, y = 0.75): 3D Cyan Bar Columns Standing Tall!
        const topY = 0.75;

        // Top perimeter
        const topRectPoints = [
          new THREE.Vector3(-halfSize, topY, -halfSize),
          new THREE.Vector3(halfSize, topY, -halfSize),
          new THREE.Vector3(halfSize, topY, halfSize),
          new THREE.Vector3(-halfSize, topY, halfSize),
          new THREE.Vector3(-halfSize, topY, -halfSize),
        ];
        const topRectGeo = new THREE.BufferGeometry().setFromPoints(topRectPoints);
        currentModelGroup.add(new THREE.Line(topRectGeo, cyanLineMat));

        // 5 Vertical 3D Bar Columns on Top Layer (as shown in reference image!)
        // Heights: medium, tall, taller, tallest, medium-tall
        const barHeights = [0.55, 0.95, 0.75, 1.25, 0.65];
        const barWidth = 0.22;

        barHeights.forEach((hVal, idx) => {
          const bx = -0.65 + idx * 0.32;
          const bz = -0.35 + (idx % 2) * 0.25;

          const colGeo = new THREE.BoxGeometry(barWidth, hVal, barWidth);
          const colMesh = new THREE.Mesh(colGeo, cyanFillMat);
          colMesh.position.set(bx, topY + hVal / 2, bz);

          // Glowing wireframe borders
          const colWire = new THREE.LineSegments(new THREE.EdgesGeometry(colGeo), brightCyanLineMat);
          colMesh.add(colWire);

          // Bright Glowing Top Cap
          const capGeo = new THREE.PlaneGeometry(barWidth, barWidth);
          const capMesh = new THREE.Mesh(capGeo, columnTopMat);
          capMesh.rotation.x = -Math.PI / 2;
          capMesh.position.set(0, hVal / 2 + 0.005, 0);
          colMesh.add(capMesh);

          currentModelGroup.add(colMesh);
        });

        // 4 Vertical Isometric Guide Corner Pillars (linking all 3 planes!)
        const corners = [
          [-halfSize, -halfSize],
          [halfSize, -halfSize],
          [halfSize, halfSize],
          [-halfSize, halfSize],
        ];

        corners.forEach(([cx, cz]) => {
          const pillarPoints = [
            new THREE.Vector3(cx, bottomY, cz),
            new THREE.Vector3(cx, topY, cz),
          ];
          const pillarGeo = new THREE.BufferGeometry().setFromPoints(pillarPoints);
          currentModelGroup.add(new THREE.Line(pillarGeo, cyanLineMat));

          // Corner node dots
          [bottomY, midY, topY].forEach((py) => {
            const nodeDot = new THREE.Mesh(
              new THREE.SphereGeometry(0.025, 8, 8),
              columnTopMat
            );
            nodeDot.position.set(cx, py, cz);
            currentModelGroup.add(nodeDot);
          });
        });
      }

      scene.add(currentModelGroup);
    };

    buildModel(typeRef.current);

    // Watch for model type changes
    let lastType = typeRef.current;
    let frameId: number;
    const clock = new THREE.Clock();

    const animate = () => {
      frameId = requestAnimationFrame(animate);
      const time = clock.getElapsedTime();

      if (typeRef.current !== lastType) {
        lastType = typeRef.current;
        buildModel(lastType);
      }

      // If viewing default architecture schematic: keep isometric fixed perspective with gentle breathing hover
      if (lastType === 'architecture') {
        currentModelGroup.rotation.y = 0;
        currentModelGroup.position.y = Math.sin(time * 1.4) * 0.03;
      } else {
        // Interactive prompt models rotate slowly for inspection
        currentModelGroup.rotation.y = time * 0.35;
      }

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
      renderer.dispose();
    };
  }, []);

  return (
    <div 
      ref={containerRef} 
      className="w-full h-full relative flex items-center justify-center cursor-pointer select-none"
      title="Dynamic 3D Visual Hub Isometric Schematic"
    />
  );
};
