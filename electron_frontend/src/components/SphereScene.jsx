import React, { useRef, useEffect } from 'react';
import * as THREE from 'three';

const CONFIG = {
  particleCount: 1500,
  sphereRadius: 2.0,
  rotSpeed: 0.08,
  pulseSpeed: 0.8,          // Slower idle breathing (was 2.0)
  starCount: 5000,
  starFieldRadius: 50,
  connectionDistance: 1.0,
  maxConnections: 4,
};

// Colors
const SPHERE_COLOR = 0x2763d1;
const BG_SPHERE_COLOR = 0x1e4a8a;

export default function SphereScene({ audioLevel = 0 }) {
  const containerRef = useRef(null);
  const sceneRef = useRef(null);
  const [hasError, setHasError] = React.useState(false);
  const audioLevelRef = useRef(audioLevel);
  const smoothAudioRef = useRef(0); // Extra smoothing for sphere animation

  useEffect(() => { audioLevelRef.current = audioLevel; }, [audioLevel]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Bail out if WebGL isn't available (GPU crash, headless, etc.)
    let renderer = null;
    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'high-performance' });
    } catch (e) {
      console.warn('[Sphere] WebGL not available:', e.message);
      setHasError(true);
      return;
    }

    // ── Scene Setup ──
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x050810, 0.0025);

    const aspect = container.clientWidth / container.clientHeight;
    const camera = new THREE.PerspectiveCamera(60, aspect, 0.1, 100);
    camera.position.set(0, 1.2, 6.5);
    camera.lookAt(0, 0, 0);

    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);

    // ── Background Sphere ──
    // Uniform surface distribution — all particles at same radius, no stragglers near camera
    function createBackgroundSphere() {
      const geo = new THREE.BufferGeometry();
      const positions = new Float32Array(CONFIG.starCount * 3);
      for (let i = 0; i < CONFIG.starCount; i++) {
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos(2 * Math.random() - 1);
        const r = CONFIG.starFieldRadius;
        positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
        positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
        positions[i * 3 + 2] = r * Math.cos(phi);
      }
      geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      const mat = new THREE.PointsMaterial({
        color: BG_SPHERE_COLOR,
        size: 0.20,
        transparent: true,
        opacity: 0.65,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        sizeAttenuation: true,
      });
      const mesh = new THREE.Points(geo, mat);
      scene.add(mesh);
      return mesh;
    }

    // ── Center Sphere Builder (fixed color) ──
    function createSphere(count, radius, size) {
      const geo = new THREE.BufferGeometry();
      const positions = new Float32Array(count * 3);
      const directions = new Float32Array(count * 3);
      for (let i = 0; i < count; i++) {
        const goldenRatio = (1 + Math.sqrt(5)) / 2;
        const inc = Math.acos(1 - 2 * (i + 0.5) / count);
        const az = 2 * Math.PI * i / goldenRatio;
        const x = Math.sin(inc) * Math.cos(az);
        const y = Math.sin(inc) * Math.sin(az);
        const z = Math.cos(inc);
        directions[i * 3] = x; directions[i * 3 + 1] = y; directions[i * 3 + 2] = z;
        positions[i * 3] = x * radius; positions[i * 3 + 1] = y * radius; positions[i * 3 + 2] = z * radius;
      }
      geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      const mat = new THREE.PointsMaterial({
        color: SPHERE_COLOR,
        size,
        transparent: true,
        opacity: 0.85,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        sizeAttenuation: true,
      });
      const mesh = new THREE.Points(geo, mat);
      scene.add(mesh);
      return { mesh, geo, mat, directions };
    }

    // ── Connections ──
    function computeNeighbors(directions, count, angleThreshold, maxPerParticle) {
      const thresholdSq = angleThreshold * angleThreshold;
      const pairs = [];
      const connectionCounts = new Uint8Array(count);
      for (let i = 0; i < count; i++) {
        const ix = directions[i * 3], iy = directions[i * 3 + 1], iz = directions[i * 3 + 2];
        for (let j = i + 1; j < count; j++) {
          if (connectionCounts[i] >= maxPerParticle) break;
          if (connectionCounts[j] >= maxPerParticle) continue;
          const dx = ix - directions[j * 3], dy = iy - directions[j * 3 + 1], dz = iz - directions[j * 3 + 2];
          if (dx * dx + dy * dy + dz * dz < thresholdSq) {
            pairs.push(i, j);
            connectionCounts[i]++; connectionCounts[j]++;
          }
        }
      }
      return new Uint16Array(pairs);
    }

    function buildLineSegments(pairs, directions, baseRadius, colorHex, baseOpacity) {
      const numLines = pairs.length / 2;
      if (numLines === 0) {
        const emptyGeo = new THREE.BufferGeometry();
        emptyGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(0), 3));
        return new THREE.LineSegments(emptyGeo, new THREE.LineBasicMaterial({ color: colorHex, transparent: true, opacity: baseOpacity }));
      }
      const positions = new Float32Array(numLines * 6);
      for (let k = 0; k < numLines; k++) {
        const i = pairs[k * 2], j = pairs[k * 2 + 1];
        const off = k * 6;
        positions[off] = directions[i * 3] * baseRadius;
        positions[off + 1] = directions[i * 3 + 1] * baseRadius;
        positions[off + 2] = directions[i * 3 + 2] * baseRadius;
        positions[off + 3] = directions[j * 3] * baseRadius;
        positions[off + 4] = directions[j * 3 + 1] * baseRadius;
        positions[off + 5] = directions[j * 3 + 2] * baseRadius;
      }
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      const mat = new THREE.LineBasicMaterial({ color: colorHex, transparent: true, opacity: baseOpacity, blending: THREE.AdditiveBlending, depthWrite: false });
      const lines = new THREE.LineSegments(geo, mat);
      lines.frustumCulled = false;
      lines.userData = { pairs, directions, baseRadius, baseOpacity };
      return lines;
    }

    function updateLinePositions(lines, currentRadius) {
      const { pairs, directions } = lines.userData;
      const posAttr = lines.geometry.attributes.position;
      const array = posAttr.array;
      const numLines = pairs.length / 2;
      for (let k = 0; k < numLines; k++) {
        const i = pairs[k * 2], j = pairs[k * 2 + 1];
        const off = k * 6;
        array[off] = directions[i * 3] * currentRadius;
        array[off + 1] = directions[i * 3 + 1] * currentRadius;
        array[off + 2] = directions[i * 3 + 2] * currentRadius;
        array[off + 3] = directions[j * 3] * currentRadius;
        array[off + 4] = directions[j * 3 + 1] * currentRadius;
        array[off + 5] = directions[j * 3 + 2] * currentRadius;
      }
      posAttr.needsUpdate = true;
    }

    // ── Create scene objects ──
    const bgSphere = createBackgroundSphere();

    // Center sphere (was "inner" — the one the user sees and wants to keep)
    const sphere = createSphere(CONFIG.particleCount, CONFIG.sphereRadius, 0.05);
    const pairs = computeNeighbors(sphere.directions, CONFIG.particleCount, CONFIG.connectionDistance / CONFIG.sphereRadius, CONFIG.maxConnections);
    const lines = buildLineSegments(pairs, sphere.directions, CONFIG.sphereRadius, SPHERE_COLOR, 0.15);
    scene.add(lines);

    // ── HUD Rings around the center sphere ──
    function createRing(radius, yScale, zScale, yOffset, color, opacity) {
      const mat = new THREE.LineBasicMaterial({ color, transparent: true, opacity, blending: THREE.AdditiveBlending });
      const segments = 80;
      const pts = [];
      for (let i = 0; i <= segments; i++) {
        const theta = (i / segments) * Math.PI * 2;
        const x = radius * Math.cos(theta);
        const y = (yOffset || 0) + (yScale || 1) * radius * Math.sin(theta);
        const z = (zScale || 1) * radius * Math.sin(theta);
        pts.push(new THREE.Vector3(x, y, z));
      }
      const geo = new THREE.BufferGeometry().setFromPoints(pts);
      const line = new THREE.Line(geo, mat);
      scene.add(line);
      return line;
    }
    const ring1 = createRing(CONFIG.sphereRadius + 0.2, 0, 0.8, 0, SPHERE_COLOR, 0.10);
    const ring2 = createRing(CONFIG.sphereRadius + 0.5, 0.3, 0.7, 0, SPHERE_COLOR, 0.10);
    const ring3 = createRing(CONFIG.sphereRadius + 0.8, 0, 1, 0, SPHERE_COLOR, 0.08);
    const ring4 = createRing(CONFIG.sphereRadius + 1.1, 0.3, 0.7, 0, SPHERE_COLOR, 0.06);

    // ── Resize ──
    function onResize() {
      const w = container.clientWidth;
      const h = container.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    }
    window.addEventListener('resize', onResize);

    // ── Animation Loop ──
    let animId;
    function animate() {
      animId = requestAnimationFrame(animate);
      const time = Date.now() * 0.001;
      const aLvl = audioLevelRef.current;
      // Additional smoothing for sphere — slow exponential decay prevents
      // the "violent shaking" when TTS audio levels jump rapidly
      smoothAudioRef.current += (aLvl - smoothAudioRef.current) * 0.10;
      const sLvl = smoothAudioRef.current; // smoothed level for sphere animation

      const audioBoost = 1 + sLvl * 2.0;
      const scale = 1 + 0.06 * Math.sin(time * CONFIG.pulseSpeed) + sLvl * 0.15;
      const radius = CONFIG.sphereRadius * scale;

      // Rotation
      sphere.mesh.rotation.y += CONFIG.rotSpeed * 0.003 * audioBoost;
      lines.rotation.y += CONFIG.rotSpeed * 0.003 * audioBoost;

      // Update particle positions
      const updatePositions = (particles, radius) => {
        const pos = particles.geo.attributes.position;
        const dir = particles.directions;
        const array = pos.array;
        const count = pos.count;
        for (let i = 0; i < count; i++) {
          const i3 = i * 3;
          array[i3] = dir[i3] * radius;
          array[i3 + 1] = dir[i3 + 1] * radius;
          array[i3 + 2] = dir[i3 + 2] * radius;
        }
        pos.needsUpdate = true;
      };
      updatePositions(sphere, radius);

      // Update lines
      updateLinePositions(lines, radius);

      // Line opacity
      lines.material.opacity = 0.08 + sLvl * 0.2 + 0.02 * Math.sin(time * 0.4);
      sphere.mat.size = 0.05 * (1 + sLvl * 1.5);

      // Rings — 4 rings with varying orbital speeds
      ring1.rotation.y += 0.003 * audioBoost;
      ring2.rotation.y += 0.0025 * audioBoost;
      ring2.rotation.x += 0.001 * audioBoost;
      ring3.rotation.y += 0.002 * audioBoost;
      ring4.rotation.y += 0.0015 * audioBoost;
      ring4.rotation.x += 0.0008 * audioBoost;

      // Background sphere
      bgSphere.rotation.y += 0.0002;
      bgSphere.rotation.x += 0.0001;

      // Camera sway
      camera.position.x = Math.sin(time * 0.1) * 0.08;
      camera.position.y = 1.2 + Math.cos(time * 0.12) * 0.05;
      camera.lookAt(0, 0, 0);

      renderer.render(scene, camera);
    }
    animate();

    // ── Store scene refs for audio updates ──
    sceneRef.current = { scene, camera, renderer, sphere, lines, bgSphere, ring1, ring2, ring3, ring4, onResize, animId };

    // ── Cleanup ──
    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', onResize);
      renderer.dispose();
      if (renderer.domElement.parentElement) {
        renderer.domElement.parentElement.removeChild(renderer.domElement);
      }
      scene.traverse((obj) => {
        if (obj.geometry) obj.geometry.dispose();
        if (obj.material) obj.material.dispose();
      });
    };
  }, []); // Only mount once

  return hasError ? (
    <div className="fixed inset-0 z-0"
      style={{
        pointerEvents: 'none',
        background: 'radial-gradient(ellipse at center, rgba(10,20,40,0.8) 0%, transparent 70%)',
      }}
    />
  ) : (
    <div
      ref={containerRef}
      className="fixed inset-0 z-0"
      style={{ pointerEvents: 'none' }}
    />
  );
}
