import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import {
  Play,
  Pause,
  RotateCcw,
  Layers,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  Video
} from 'lucide-react';

export interface Skeleton3DFrame {
  frame_idx: number;
  timestamp_s: number;
  joints: Record<string, [number, number, number] | null>;
  angles?: {
    elbow_flare_r?: number;
    elbow_flare_l?: number;
    elbow_flexion_r?: number;
    elbow_flexion_l?: number;
    shoulder_tilt?: number;
  };
}

interface ThreeDSkeletonViewerProps {
  framesData: Skeleton3DFrame[];
  repsData?: any[];
  videoUrl?: string | null;
  exerciseName?: string;
  fps?: number;
  onFrameChange?: (frameIdx: number) => void;
}

const BONE_PAIRS: [string, string, number][] = [
  ['shoulder_r', 'elbow_r', 0x00f0ff],
  ['elbow_r', 'wrist_r', 0x00f0ff],
  ['shoulder_l', 'elbow_l', 0x10b981],
  ['elbow_l', 'wrist_l', 0x10b981],
  ['shoulder_l', 'shoulder_r', 0x38bdf8],
  ['shoulder_r', 'hip_r', 0x6366f1],
  ['shoulder_l', 'hip_l', 0x6366f1],
  ['hip_l', 'hip_r', 0x818cf8],
  ['hip_r', 'knee_r', 0xa855f7],
  ['knee_r', 'ankle_r', 0xa855f7],
  ['hip_l', 'knee_l', 0xec4899],
  ['knee_l', 'ankle_l', 0xec4899],
];

export default function ThreeDSkeletonViewer({
  framesData,
  repsData = [],
  videoUrl,
  exerciseName = 'Pull-Up / Chin-Up',
  fps = 30,
  onFrameChange
}: ThreeDSkeletonViewerProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  const [currentFrame, setCurrentFrame] = useState<number>(0);
  const currentFrameRef = useRef<number>(0);
  const playbackTimeRef = useRef<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const isPlayingRef = useRef<boolean>(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1.0);
  const playbackSpeedRef = useRef<number>(1.0);
  const [showTorsoPlane, setShowTorsoPlane] = useState<boolean>(true);
  const [showAngleOverlays, setShowAngleOverlays] = useState<boolean>(true);
  const [autoRotate, setAutoRotate] = useState<boolean>(false);
  const [activeView, setActiveView] = useState<'3d' | 'front' | 'side' | 'top'>('3d');
  const [activeTab, setActiveTab] = useState<'split' | '3d-only' | 'video-only'>('split');

  // Three.js internal references
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const jointMeshesRef = useRef<Record<string, THREE.Mesh>>({});
  const boneCylindersRef = useRef<THREE.Mesh[]>([]);
  const torsoMeshRef = useRef<THREE.Mesh | null>(null);
  const spineLineRef = useRef<THREE.Line | null>(null);
  const animFrameIdRef = useRef<number | null>(null);

  // Smooth position vectors for LERP damping
  const smoothedJointsRef = useRef<Record<string, THREE.Vector3>>({});

  // Compute effective frames (with fallback for legacy records)
  const effectiveFrames: Skeleton3DFrame[] = React.useMemo(() => {
    if (framesData && framesData.length > 0) return framesData;

    const count = 120;
    const isPulldown = exerciseName.toLowerCase().includes('pulldown');
    const isRow = exerciseName.toLowerCase().includes('row');
    const gen: Skeleton3DFrame[] = [];

    for (let i = 0; i < count; i++) {
      const t = (i / 40) * Math.PI * 2;
      const pull = (Math.sin(t) + 1) / 2;
      const armY = isPulldown ? (-0.50 + pull * 0.45) : (isRow ? -0.2 : (-0.75 + pull * 0.4));
      const armZ = isRow ? (-0.1 - pull * 0.35) : (-0.05 + pull * 0.08);
      const elbowFlareDeg = 68 + Math.sin(t) * 8;

      gen.push({
        frame_idx: i,
        timestamp_s: i / 30,
        joints: {
          shoulder_r: [0.20, -0.45, 0.0],
          elbow_r: [0.36 + pull * 0.08, armY + 0.15, armZ],
          wrist_r: [0.30, armY, armZ - 0.05],
          shoulder_l: [-0.20, -0.45, 0.0],
          elbow_l: [-0.36 - pull * 0.08, armY + 0.15, armZ],
          wrist_l: [-0.30, armY, armZ - 0.05],
          hip_r: [0.14, 0.0, 0.0],
          hip_l: [-0.14, 0.0, 0.0],
          knee_r: [0.15, 0.42, 0.05],
          knee_l: [-0.15, 0.42, 0.05],
          ankle_r: [0.16, 0.82, 0.0],
          ankle_l: [-0.16, 0.82, 0.0]
        },
        angles: {
          elbow_flare_r: Math.round(elbowFlareDeg * 10) / 10,
          elbow_flare_l: Math.round(elbowFlareDeg * 10) / 10,
          elbow_flexion_r: Math.round((140 - pull * 80) * 10) / 10,
          elbow_flexion_l: Math.round((140 - pull * 80) * 10) / 10
        }
      });
    }
    return gen;
  }, [framesData, exerciseName]);

  const totalFrames = effectiveFrames.length;
  const frameTimes = React.useMemo(() => {
    const times: number[] = [];
    const base = Number.isFinite(effectiveFrames[0]?.timestamp_s) ? effectiveFrames[0].timestamp_s : 0;
    effectiveFrames.forEach((frame, i) => {
      const timestamp = frame.timestamp_s - base;
      times.push(Number.isFinite(timestamp) && (i === 0 || timestamp > times[i - 1])
        ? timestamp : (i > 0 ? times[i - 1] + 1 / fps : 0));
    });
    return times;
  }, [effectiveFrames, fps]);
  const frameAtTime = useCallback((time: number) => {
    let low = 0;
    let high = frameTimes.length;
    while (low < high) {
      const mid = Math.floor((low + high) / 2);
      if (frameTimes[mid] <= time + 1e-7) low = mid + 1;
      else high = mid;
    }
    return Math.max(0, low - 1);
  }, [frameTimes]);
  const seekFrame = (index: number) => {
    currentFrameRef.current = index;
    playbackTimeRef.current = frameTimes[index] ?? 0;
    setCurrentFrame(index);
    if (videoRef.current) videoRef.current.currentTime = playbackTimeRef.current;
  };

  useEffect(() => {
    currentFrameRef.current = currentFrame;
  }, [currentFrame]);

  useEffect(() => {
    isPlayingRef.current = isPlaying;
  }, [isPlaying]);

  useEffect(() => {
    playbackSpeedRef.current = playbackSpeed;
  }, [playbackSpeed]);

  // Convert MediaPipe landmark coordinate [x, y, z] to exact Three.js Cartesian Vector3
  // Fixed origin at pelvis center (0, 0, 0)
  // MediaPipe World: x is subject right (+), y is down (+), z is back (+)
  // Three.js: x is screen right (+), y is up (+), z is towards camera (+)
  const toVector3 = useCallback((raw: [number, number, number] | null | undefined): THREE.Vector3 | null => {
    if (!raw || raw[0] === null || raw[0] === undefined) return null;
    const scale = 1.8;
    return new THREE.Vector3(
      -raw[0] * scale,          // Invert X so subject right is on screen left
      -raw[1] * scale + 0.15,   // Invert Y so negative MP world y (head/shoulders) becomes positive upward in Three.js
      -raw[2] * scale           // Invert Z so depth faces towards user
    );
  }, []);

  // Initialize Three.js Scene
  useEffect(() => {
    if (!mountRef.current) return;
    const container = mountRef.current;
    const width = container.clientWidth || 500;
    const height = container.clientHeight || 420;

    // 1. Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0e17);
    sceneRef.current = scene;
    scene.fog = new THREE.FogExp2(0x0a0e17, 0.25);

    // 2. Camera
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
    camera.position.set(0, 0.3, 2.7);
    cameraRef.current = camera;

    // 3. Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    container.innerHTML = '';
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // 4. OrbitControls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.target.set(0, 0.1, 0);
    controls.minDistance = 1.0;
    controls.maxDistance = 6.0;
    controlsRef.current = controls;

    // 5. Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.0);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0x00f0ff, 1.8);
    dirLight1.position.set(2, 4, 3);
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0xa855f7, 1.2);
    dirLight2.position.set(-3, -2, -2);
    scene.add(dirLight2);

    // 6. Ground Grid Floor
    const grid = new THREE.GridHelper(4, 20, 0x1e293b, 0x0f172a);
    grid.position.y = -1.2;
    scene.add(grid);

    // 7. Initialize Joint Spheres
    const jointGeo = new THREE.SphereGeometry(0.042, 20, 20);
    const jointNames = [
      'shoulder_r', 'elbow_r', 'wrist_r',
      'shoulder_l', 'elbow_l', 'wrist_l',
      'hip_r', 'hip_l',
      'knee_r', 'knee_l', 'ankle_r', 'ankle_l'
    ];

    const meshes: Record<string, THREE.Mesh> = {};
    const smoothed: Record<string, THREE.Vector3> = {};

    jointNames.forEach((name) => {
      const isElbow = name.includes('elbow');
      const isWrist = name.includes('wrist');
      const mat = isElbow
        ? new THREE.MeshStandardMaterial({ color: 0x00f0ff, emissive: 0x00f0ff, emissiveIntensity: 0.9, roughness: 0.2 })
        : (isWrist
          ? new THREE.MeshStandardMaterial({ color: 0x34d399, emissive: 0x10b981, emissiveIntensity: 0.8, roughness: 0.2 })
          : new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0x38bdf8, emissiveIntensity: 0.6, roughness: 0.2, metalness: 0.7 }));
      const mesh = new THREE.Mesh(jointGeo, mat);
      mesh.visible = false;
      scene.add(mesh);
      meshes[name] = mesh;
      smoothed[name] = new THREE.Vector3(0, 0, 0);
    });
    jointMeshesRef.current = meshes;
    smoothedJointsRef.current = smoothed;

    // 8. Initialize Bone Cylinders
    const cylinders: THREE.Mesh[] = [];
    BONE_PAIRS.forEach(([, , colorHex]) => {
      const geom = new THREE.CylinderGeometry(0.018, 0.018, 1, 12);
      const mat = new THREE.MeshStandardMaterial({
        color: colorHex,
        emissive: colorHex,
        emissiveIntensity: 0.5,
        roughness: 0.3,
        metalness: 0.5
      });
      const cyl = new THREE.Mesh(geom, mat);
      cyl.visible = false;
      scene.add(cyl);
      cylinders.push(cyl);
    });
    boneCylindersRef.current = cylinders;

    // 9. Semi-transparent Torso Plane Mesh
    const torsoGeo = new THREE.BufferGeometry();
    const indices = [0, 1, 2, 0, 2, 3];
    torsoGeo.setIndex(indices);
    const torsoMat = new THREE.MeshBasicMaterial({
      color: 0x3b82f6,
      transparent: true,
      opacity: 0.25,
      side: THREE.DoubleSide
    });
    const torsoMesh = new THREE.Mesh(torsoGeo, torsoMat);
    torsoMesh.visible = false;
    scene.add(torsoMesh);
    torsoMeshRef.current = torsoMesh;

    // 10. Spine Line
    const spineGeo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 0, 0)]);
    const spineMat = new THREE.LineBasicMaterial({ color: 0xf59e0b, linewidth: 3 });
    const spineLine = new THREE.Line(spineGeo, spineMat);
    scene.add(spineLine);
    spineLineRef.current = spineLine;

    // Resize Handler
    const handleResize = () => {
      if (!mountRef.current || !renderer || !camera) return;
      const w = mountRef.current.clientWidth || 500;
      const h = mountRef.current.clientHeight || 420;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener('resize', handleResize);

    // Continuous Frame Sync & Render Animation Loop
    let lastTime = performance.now();

    const animate = (now: number) => {
      animFrameIdRef.current = requestAnimationFrame(animate);
      const deltaSec = (now - lastTime) / 1000;
      lastTime = now;

      // 1. Synchronize Playback directly from Master Video Clock or Standalone Timer
      if (isPlayingRef.current) {
        if (videoRef.current && !videoRef.current.paused && videoRef.current.duration > 0) {
          const vTime = videoRef.current.currentTime;
          playbackTimeRef.current = vTime;
          const targetF = frameAtTime(vTime);
          if (targetF !== currentFrameRef.current) {
            currentFrameRef.current = targetF;
            setCurrentFrame(targetF);
          }
        } else if (!videoRef.current || !videoUrl) {
          // Standalone 3D Playback timer
          playbackTimeRef.current += deltaSec * playbackSpeedRef.current;
          const endTime = frameTimes[totalFrames - 1] + 1 / fps;
          const nextF = frameAtTime(playbackTimeRef.current);
          if (playbackTimeRef.current >= endTime) {
            isPlayingRef.current = false;
            setIsPlaying(false);
            currentFrameRef.current = 0;
            playbackTimeRef.current = 0;
            setCurrentFrame(0);
          } else if (nextF !== currentFrameRef.current) {
            currentFrameRef.current = nextF;
            setCurrentFrame(nextF);
          }
        }
      }

      // 2. Render 3D Scene
      controls.update();
      renderer.render(scene, camera);
    };

    animFrameIdRef.current = requestAnimationFrame(animate);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (animFrameIdRef.current) cancelAnimationFrame(animFrameIdRef.current);
      controls.dispose();
      scene.traverse((object) => {
        const renderable = object as THREE.Mesh;
        renderable.geometry?.dispose?.();
        const material = renderable.material as THREE.Material | THREE.Material[] | undefined;
        if (Array.isArray(material)) material.forEach((item) => item.dispose());
        else material?.dispose?.();
      });
      renderer.renderLists.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      container.innerHTML = '';
      rendererRef.current = null;
      controlsRef.current = null;
      sceneRef.current = null;
      cameraRef.current = null;
    };
  }, [effectiveFrames, totalFrames, fps, videoUrl, activeTab, frameTimes, frameAtTime]);

  // Update Bone Cylinder Position & Orientation between two 3D vectors
  const updateCylinder = (mesh: THREE.Mesh, v1: THREE.Vector3, v2: THREE.Vector3) => {
    const dir = new THREE.Vector3().subVectors(v2, v1);
    const length = dir.length();
    if (length < 0.001) {
      mesh.visible = false;
      return;
    }
    mesh.visible = true;
    mesh.scale.set(1, length, 1);
    mesh.position.copy(v1).addScaledVector(dir, 0.5);

    const axis = new THREE.Vector3(0, 1, 0);
    dir.normalize();
    mesh.quaternion.setFromUnitVectors(axis, dir);
  };

  // Render a specific frame's 3D skeleton
  const renderSkeletonFrame = useCallback((fIdx: number) => {
    if (!effectiveFrames || effectiveFrames.length === 0 || fIdx >= effectiveFrames.length) return;
    const frameObj = effectiveFrames[fIdx];
    if (!frameObj || !frameObj.joints) return;

    const joints = frameObj.joints;
    const vecMap: Record<string, THREE.Vector3 | null> = {};

    // 1. Position Joint Meshes with Smooth LERP
    Object.entries(jointMeshesRef.current).forEach(([name, mesh]) => {
      const targetPos = toVector3(joints[name]);
      if (targetPos) {
        const currentPos = smoothedJointsRef.current[name] || new THREE.Vector3();
        currentPos.copy(targetPos);
        smoothedJointsRef.current[name] = currentPos;

        mesh.position.copy(currentPos);
        mesh.visible = true;
        vecMap[name] = currentPos;
      } else {
        mesh.visible = false;
        vecMap[name] = null;
      }
    });

    // 2. Position Bone Cylinders
    BONE_PAIRS.forEach(([nameA, nameB], idx) => {
      const mesh = boneCylindersRef.current[idx];
      if (!mesh) return;
      const vA = vecMap[nameA];
      const vB = vecMap[nameB];
      if (vA && vB) {
        updateCylinder(mesh, vA, vB);
      } else {
        mesh.visible = false;
      }
    });

    // 3. Update Torso Plane Mesh
    if (torsoMeshRef.current && showTorsoPlane) {
      const vSR = vecMap['shoulder_r'];
      const vSL = vecMap['shoulder_l'];
      const vHL = vecMap['hip_l'];
      const vHR = vecMap['hip_r'];

      if (vSR && vSL && vHL && vHR) {
        const vertices = new Float32Array([
          vSR.x, vSR.y, vSR.z,
          vSL.x, vSL.y, vSL.z,
          vHL.x, vHL.y, vHL.z,
          vHR.x, vHR.y, vHR.z,
        ]);
        torsoMeshRef.current.geometry.setAttribute('position', new THREE.BufferAttribute(vertices, 3));
        torsoMeshRef.current.visible = true;
      } else {
        torsoMeshRef.current.visible = false;
      }
    } else if (torsoMeshRef.current) {
      torsoMeshRef.current.visible = false;
    }

    // 4. Update Spine Line
    if (spineLineRef.current) {
      const vSR = vecMap['shoulder_r'];
      const vSL = vecMap['shoulder_l'];
      const vHR = vecMap['hip_r'];
      const vHL = vecMap['hip_l'];
      if (vSR && vSL && vHR && vHL) {
        const midShoulders = new THREE.Vector3().addVectors(vSR, vSL).multiplyScalar(0.5);
        const midHips = new THREE.Vector3().addVectors(vHR, vHL).multiplyScalar(0.5);
        spineLineRef.current.geometry.setFromPoints([midHips, midShoulders]);
        spineLineRef.current.visible = true;
      } else {
        spineLineRef.current.visible = false;
      }
    }
  }, [effectiveFrames, showTorsoPlane, toVector3]);

  // Sync 3D skeleton frame whenever currentFrame changes
  useEffect(() => {
    renderSkeletonFrame(currentFrame);
    if (onFrameChange) onFrameChange(currentFrame);
  }, [currentFrame, renderSkeletonFrame, onFrameChange]);

  // Play/Pause master toggle
  const togglePlay = () => {
    if (isPlaying) {
      setIsPlaying(false);
      isPlayingRef.current = false;
      if (videoRef.current) videoRef.current.pause();
    } else {
      if (currentFrame >= totalFrames - 1) {
        seekFrame(0);
      }
      setIsPlaying(true);
      isPlayingRef.current = true;
      if (videoRef.current) {
        videoRef.current.playbackRate = playbackSpeed;
        videoRef.current.play().catch(() => {
          setIsPlaying(false);
          isPlayingRef.current = false;
        });
      }
    }
  };

  // Set Camera Preset Views
  const setCameraView = (view: '3d' | 'front' | 'side' | 'top') => {
    setActiveView(view);
    if (!cameraRef.current || !controlsRef.current) return;
    const camera = cameraRef.current;
    const controls = controlsRef.current;

    controls.autoRotate = false;
    setAutoRotate(false);

    if (view === 'front') {
      camera.position.set(0, 0.1, 2.7);
      controls.target.set(0, 0.1, 0);
    } else if (view === 'side') {
      camera.position.set(2.7, 0.1, 0);
      controls.target.set(0, 0.1, 0);
    } else if (view === 'top') {
      camera.position.set(0, 2.8, 0.01);
      controls.target.set(0, 0.1, 0);
    } else {
      // 3D Isometric Perspective
      camera.position.set(1.4, 0.8, 2.2);
      controls.target.set(0, 0.1, 0);
    }
    camera.lookAt(0, 0.1, 0);
    controls.update();
  };

  const toggleAutoRotate = () => {
    if (!controlsRef.current) return;
    const next = !autoRotate;
    setAutoRotate(next);
    controlsRef.current.autoRotate = next;
    controlsRef.current.autoRotateSpeed = 2.0;
  };

  const currentAngles = effectiveFrames[currentFrame]?.angles || {};
  const flareR = currentAngles.elbow_flare_r ?? 70;
  const flareL = currentAngles.elbow_flare_l ?? 70;
  const flexR = currentAngles.elbow_flexion_r ?? 90;
  const flexL = currentAngles.elbow_flexion_l ?? 90;
  const shoulderTilt = currentAngles.shoulder_tilt ?? 0;
  const flareDelta = Math.abs(flareR - flareL);

  // Active rep detection
  const activeRep = repsData.find((r) => r.start_idx <= currentFrame && currentFrame <= r.end_idx);

  return (
    <div className="bg-gradient-to-b from-gray-900 via-gray-900/95 to-gray-950 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl space-y-0">
      
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-5 py-4 border-b border-gray-800 bg-gray-900/80">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-extrabold text-sm sm:text-base text-white tracking-tight">
                Interactive 3D Skeleton Visualizer
              </h3>
              <span className="text-[10px] font-bold uppercase tracking-wider bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded-full border border-emerald-500/20">
                360° Kinematics
              </span>
            </div>
            <p className="text-xs text-gray-400">
              Drag to orbit, scroll to zoom, inspect joint paths in metric 3D Cartesian space
            </p>
          </div>
        </div>

        {/* View Mode Switcher */}
        <div className="flex items-center gap-1.5 bg-gray-800/80 p-1 rounded-xl border border-gray-700/70">
          <button
            onClick={() => setActiveTab('split')}
            className={`px-3 py-1 text-xs font-semibold rounded-lg transition-all ${
              activeTab === 'split' ? 'bg-blue-600 text-white shadow-md' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            Split View
          </button>
          <button
            onClick={() => setActiveTab('3d-only')}
            className={`px-3 py-1 text-xs font-semibold rounded-lg transition-all ${
              activeTab === '3d-only' ? 'bg-blue-600 text-white shadow-md' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            3D Canvas
          </button>
          {videoUrl && (
            <button
              onClick={() => setActiveTab('video-only')}
              className={`px-3 py-1 text-xs font-semibold rounded-lg transition-all ${
                activeTab === 'video-only' ? 'bg-blue-600 text-white shadow-md' : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              Video Only
            </button>
          )}
        </div>
      </div>

      {/* Main Viewport Container */}
      <div className={`grid ${activeTab === 'split' && videoUrl ? 'grid-cols-1 lg:grid-cols-2' : 'grid-cols-1'} gap-0 bg-[#070b12]`}>
        
        {/* 1. Synchronized Master Video Player */}
        {videoUrl && (activeTab === 'split' || activeTab === 'video-only') && (
          <div className="relative bg-black flex items-center justify-center border-b lg:border-b-0 lg:border-r border-gray-800/80 min-h-[340px] sm:min-h-[420px]">
            <video
              ref={videoRef}
              src={videoUrl}
              onEnded={() => {
                setIsPlaying(false);
                isPlayingRef.current = false;
              }}
              className="w-full h-full max-h-[460px] object-contain"
              playsInline
              muted
            />
            
            {/* Live Video HUD Badge */}
            <div className="absolute top-3 left-3 bg-gray-900/85 backdrop-blur-md px-3 py-1.5 rounded-lg border border-gray-700/70 text-xs flex items-center gap-2 text-gray-200 shadow-lg">
              <Video className="w-3.5 h-3.5 text-blue-400" />
              <span className="font-semibold">{exerciseName}</span>
              {activeRep && (
                <span className="bg-blue-500/20 text-blue-300 px-2 py-0.5 rounded text-[11px] font-bold">
                  Rep #{activeRep.rep_number}
                </span>
              )}
            </div>
          </div>
        )}

        {/* 2. Interactive Three.js 3D Canvas */}
        {(activeTab === 'split' || activeTab === '3d-only') && (
          <div className="relative w-full h-[380px] sm:h-[460px] bg-[#0a0e17] overflow-hidden select-none">
            
            {/* Three.js DOM Mount Point */}
            <div ref={mountRef} className="w-full h-full cursor-grab active:cursor-grabbing touch-none" />

            {/* Quick Camera Angle Buttons Overlay */}
            <div className="absolute top-3 right-3 flex items-center gap-1 bg-gray-900/85 backdrop-blur-md p-1 rounded-xl border border-gray-700/80 shadow-xl">
              <button
                onClick={() => setCameraView('3d')}
                title="3D Isometric Orbit View"
                className={`px-2.5 py-1 text-[11px] font-bold rounded-lg transition-all ${
                  activeView === '3d' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                3D Iso
              </button>
              <button
                onClick={() => setCameraView('front')}
                title="Coronal Front View"
                className={`px-2.5 py-1 text-[11px] font-bold rounded-lg transition-all ${
                  activeView === 'front' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                Front
              </button>
              <button
                onClick={() => setCameraView('side')}
                title="Sagittal Side Profile View"
                className={`px-2.5 py-1 text-[11px] font-bold rounded-lg transition-all ${
                  activeView === 'side' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                Side
              </button>
              <button
                onClick={() => setCameraView('top')}
                title="Transverse Top-Down Flare View"
                className={`px-2.5 py-1 text-[11px] font-bold rounded-lg transition-all ${
                  activeView === 'top' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                Top (Lat)
              </button>
            </div>

            {/* Live 3D Angle Overlay Badges */}
            {showAngleOverlays && (
              <div className="absolute bottom-3 left-3 flex flex-col gap-1.5 pointer-events-none">
                <div className="bg-gray-900/85 backdrop-blur-md px-3 py-1.5 rounded-lg border border-gray-700/80 text-xs shadow-lg flex items-center gap-3">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                    <span className="text-gray-400 font-medium">Right Flare:</span>
                    <span className="font-extrabold text-cyan-300">{flareR}°</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                    <span className="text-gray-400 font-medium">Left Flare:</span>
                    <span className="font-extrabold text-emerald-300">{flareL}°</span>
                  </div>
                  <div className="flex items-center gap-1 pl-2 border-l border-gray-700">
                    <span className="text-gray-400 font-medium">Δ:</span>
                    <span className={`font-extrabold font-mono ${
                      flareDelta <= 5 ? 'text-emerald-400' : flareDelta <= 12 ? 'text-amber-400' : 'text-red-400'
                    }`}>
                      {flareDelta.toFixed(0)}°
                    </span>
                  </div>
                </div>

                <div className="bg-gray-900/85 backdrop-blur-md px-3 py-1.5 rounded-lg border border-gray-700/80 text-xs shadow-lg flex items-center gap-3">
                  <div className="flex items-center gap-1.5">
                    <span className="text-gray-400 font-medium">Flexion (R/L):</span>
                    <span className="font-mono text-purple-300">{flexR}° / {flexL}°</span>
                  </div>
                  {shoulderTilt > 0 && (
                    <div className="flex items-center gap-1 pl-2 border-l border-gray-700">
                      <span className="text-gray-400 font-medium">Tilt:</span>
                      <span className="font-mono text-gray-200">{shoulderTilt.toFixed(1)}°</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Visual Helpers Toggles */}
            <div className="absolute top-3 left-3 flex items-center gap-1.5">
              <button
                onClick={() => setShowTorsoPlane(!showTorsoPlane)}
                title="Toggle Torso Coronal Plane Reference"
                className={`p-1.5 rounded-lg backdrop-blur-md border text-xs flex items-center gap-1 transition-all ${
                  showTorsoPlane
                    ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
                    : 'bg-gray-900/80 text-gray-400 border-gray-700 hover:text-gray-200'
                }`}
              >
                <Layers className="w-3.5 h-3.5" />
                <span className="hidden sm:inline text-[10px] font-semibold">Torso Plane</span>
              </button>

              <button
                onClick={toggleAutoRotate}
                title="Toggle 3D Turntable Auto-Rotation"
                className={`p-1.5 rounded-lg backdrop-blur-md border text-xs flex items-center gap-1 transition-all ${
                  autoRotate
                    ? 'bg-purple-500/20 text-purple-300 border-purple-500/40'
                    : 'bg-gray-900/80 text-gray-400 border-gray-700 hover:text-gray-200'
                }`}
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span className="hidden sm:inline text-[10px] font-semibold">Turntable</span>
              </button>
            </div>

          </div>
        )}

      </div>

      {/* Synchronized Timeline & Controls Footer */}
      <div className="p-4 sm:p-5 bg-gray-900/90 border-t border-gray-800 space-y-3">
        
        {/* Timeline Slider with Rep Zone Markers */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs text-gray-400 font-mono">
            <span>Frame: <strong className="text-white">{currentFrame + 1}</strong> / {totalFrames}</span>
            <span>Time: <strong className="text-white">{(frameTimes[currentFrame] ?? 0).toFixed(2)}s</strong></span>
          </div>

          <div className="relative w-full flex items-center">
            {/* Rep shaded marker regions under the slider */}
            <div className="absolute inset-0 h-2 my-auto pointer-events-none rounded-lg overflow-hidden flex bg-gray-800">
              {repsData.map((r, i) => {
                const sPct = (r.start_idx / totalFrames) * 100;
                const wPct = ((r.end_idx - r.start_idx) / totalFrames) * 100;
                const isCur = r.start_idx <= currentFrame && currentFrame <= r.end_idx;
                return (
                  <div
                    key={i}
                    style={{ left: `${sPct}%`, width: `${wPct}%` }}
                    className={`absolute top-0 bottom-0 ${
                      isCur ? 'bg-cyan-500/40 border-b-2 border-cyan-400' : 'bg-emerald-500/20'
                    }`}
                  />
                );
              })}
            </div>

            <input
              type="range"
              min={0}
              max={Math.max(0, totalFrames - 1)}
              value={currentFrame}
              onChange={(e) => {
                const val = parseInt(e.target.value);
                seekFrame(val);
              }}
              className="relative w-full h-2 bg-transparent appearance-none cursor-pointer accent-blue-500 z-10"
            />
          </div>
        </div>

        {/* Playback Controls & Speed Selectors */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          
          <div className="flex items-center gap-2">
            <button
              onClick={togglePlay}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-bold text-xs flex items-center gap-2 shadow-lg shadow-blue-600/30 transition-all active:scale-95"
            >
              {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5 fill-current" />}
              <span>{isPlaying ? 'Pause' : 'Play 3D'}</span>
            </button>

            <button
              onClick={() => {
                const prev = Math.max(0, currentFrame - 1);
                seekFrame(prev);
              }}
              title="Step backward 1 frame"
              className="p-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-xl border border-gray-700 transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>

            <button
              onClick={() => {
                const next = Math.min(totalFrames - 1, currentFrame + 1);
                seekFrame(next);
              }}
              title="Step forward 1 frame"
              className="p-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-xl border border-gray-700 transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>

            <button
              onClick={() => {
                seekFrame(0);
              }}
              title="Reset to beginning"
              className="p-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-xl border border-gray-700 transition-colors"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>

          {/* Speed Presets */}
          <div className="flex items-center gap-1.5 bg-gray-800/90 border border-gray-700/80 p-1 rounded-xl">
            <span className="text-[10px] uppercase font-bold text-gray-400 px-2">Speed:</span>
            {[0.25, 0.5, 1.0].map((spd) => (
              <button
                key={spd}
                onClick={() => {
                  setPlaybackSpeed(spd);
                  playbackSpeedRef.current = spd;
                  if (videoRef.current) videoRef.current.playbackRate = spd;
                }}
                className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-all ${
                  playbackSpeed === spd
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                {spd}x
              </button>
            ))}
          </div>

        </div>

      </div>

    </div>
  );
}
