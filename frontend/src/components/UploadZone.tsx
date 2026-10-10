import React, { useState, useRef } from 'react';
import { Upload, Target, CheckCircle2, Camera, FileVideo } from 'lucide-react';
import { TrimRange, validateVideoFile } from '../lib/videoFiles';
import type { VideoUploadRequest } from '../lib/videoUploadController';
import VideoTrimmerModal from './VideoTrimmerModal';

interface UploadZoneProps {
  onSubmit: (request: VideoUploadRequest) => void;
  userId?: string;
  accessToken?: string;
  onShowToast: (toast: { type: 'success' | 'error' | 'info' | 'warning'; title: string; message?: string }) => void;
}

export const EXERCISES = [
  {
    id: 'Lat Pulldown (Lower-Lat Bias)',
    name: 'Lat Pulldown',
    subtitle: 'Lower-Lat Bias',
    flareGoal: '< 25°',
    icon: '⚡',
  },
  {
    id: 'Pull-Up / Chin-Up',
    name: 'Pull-Up / Chin-Up',
    subtitle: 'Bodyweight Vertical Pull',
    flareGoal: '45–75°',
    icon: '🧗',
  },
  {
    id: 'Barbell Row',
    name: 'Barbell Row',
    subtitle: 'Bent-Over Row',
    flareGoal: '30–45°',
    icon: '🏋️',
  },
  {
    id: 'Seated Cable Row',
    name: 'Seated Cable Row',
    subtitle: 'Horizontal Cable Pull',
    flareGoal: '< 30°',
    icon: '🚣',
  },
  {
    id: 'Single-Arm Dumbbell Row',
    name: 'Dumbbell Row',
    subtitle: 'Unilateral Lat Focus',
    flareGoal: '< 25°',
    icon: '💪',
  },
];

export default function UploadZone({
  onSubmit,
  userId,
  accessToken,
  onShowToast,
}: UploadZoneProps) {
  const [selectedExercise, setSelectedExercise] = useState<string>(EXERCISES[0].id);
  const [userHeight, setUserHeight] = useState<string>('');
  const [dragActive, setDragActive] = useState(false);
  const [validating, setValidating] = useState(false);

  // Video Trimmer State
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [isTrimmerOpen, setIsTrimmerOpen] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndOpenTrimmer(e.dataTransfer.files[0]);
    }
  };

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      validateAndOpenTrimmer(e.target.files[0]);
    }
  };

  const validateAndOpenTrimmer = (file: File) => {
    if (validating) return;
    if (!accessToken) {
      onShowToast({
        type: 'warning',
        title: 'Sign In Required',
        message: 'Please sign in or create an account to upload and analyze your workout videos.',
      });
      return;
    }

    try {
      validateVideoFile(file);
    } catch (error) {
      onShowToast({
        type: 'error', title: 'Video Cannot Be Selected',
        message: error instanceof Error ? error.message : 'Please select a valid video.',
      });
      return;
    }

    // Open trimmer modal
    setPendingFile(file);
    setIsTrimmerOpen(true);
  };

  const handleConfirmTrim = (file: File, range: TrimRange | null) => {
    if (validating) return;
    if (!accessToken) {
      onShowToast({
        type: 'warning',
        title: 'Sign In Required',
        message: 'Please sign in or create an account to upload and analyze your workout videos.',
      });
      return;
    }

    setIsTrimmerOpen(false);
    setValidating(true);
    onSubmit({ file, range, exerciseName: selectedExercise,
      userHeightCm: userHeight ? parseFloat(userHeight) : null, userId, accessToken });
  };

  const currentExerciseObj = EXERCISES.find(e => e.id === selectedExercise) || EXERCISES[0];

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      
      {/* Exercise Selection Cards */}
      <div className="bg-gray-900/80 border border-gray-800 rounded-2xl p-6 shadow-xl backdrop-blur-sm">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Target className="w-5 h-5 text-blue-400" />
            <h3 className="text-lg font-bold text-white">Select Exercise Movement</h3>
          </div>
          <span className="text-xs text-blue-400 bg-blue-500/10 px-2.5 py-1 rounded-full border border-blue-500/20 font-medium">
            Form Target: {currentExerciseObj.flareGoal} Flare
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3">
          {EXERCISES.map((ex) => {
            const isSelected = selectedExercise === ex.id;
            return (
              <button
                key={ex.id}
                type="button"
                onClick={() => setSelectedExercise(ex.id)}
                className={`p-3.5 rounded-xl border text-left transition-all relative flex flex-col justify-between ${
                  isSelected
                    ? 'bg-gradient-to-b from-blue-900/40 to-blue-950/40 border-blue-500 shadow-md ring-1 ring-blue-500/50'
                    : 'bg-gray-800/40 border-gray-700/60 hover:bg-gray-800 hover:border-gray-600'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-2xl">{ex.icon}</span>
                    {isSelected && (
                      <CheckCircle2 className="w-4 h-4 text-blue-400 shrink-0" />
                    )}
                  </div>
                  <h4 className="font-bold text-white text-sm leading-tight">{ex.name}</h4>
                  <p className="text-[11px] text-gray-400 mt-1">{ex.subtitle}</p>
                </div>
                <div className="mt-3 pt-2 border-t border-gray-700/40 text-[10px] text-gray-400 flex items-center justify-between">
                  <span>Goal:</span>
                  <span className="font-semibold text-emerald-400">{ex.flareGoal}</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Optional Height Calibration Input */}
      <div className="bg-gray-900/60 border border-gray-800 rounded-xl px-5 py-3.5 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs shadow-md">
        <div className="text-gray-300">
          <strong className="text-white font-semibold block sm:inline mr-2">Optional Scale Calibration:</strong>
          <span>Lifter height for millimeter-calibrated VBT velocity scaling</span>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="number"
            placeholder="e.g. 178"
            value={userHeight}
            onChange={(e) => setUserHeight(e.target.value)}
            className="w-24 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-white text-xs focus:outline-none focus:border-blue-500 font-mono text-center"
          />
          <span className="text-gray-400 font-medium">cm</span>
        </div>
      </div>

      {/* Video Upload Dropzone & Mobile Camera Triggers */}
      <div 
        className={`border-2 border-dashed rounded-2xl p-8 sm:p-12 text-center transition-all shadow-xl relative overflow-hidden ${
          dragActive
            ? 'border-blue-500 bg-blue-500/10 scale-[1.005]'
            : 'border-gray-700 hover:border-gray-600 hover:bg-gray-800/40 bg-gray-900/40'
        }`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        {/* Hidden inputs for standard file picker and mobile camera */}
        <input 
          type="file" 
          ref={fileInputRef}
          id="video-upload" 
          className="hidden" 
          accept="video/*"
          onChange={handleChange}
        />
        <input 
          type="file" 
          ref={cameraInputRef}
          id="camera-upload" 
          className="hidden" 
          accept="video/*"
          capture="environment"
          onChange={handleChange}
        />

        <div className="flex flex-col items-center">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-blue-600/20 to-indigo-600/20 border border-blue-500/30 flex items-center justify-center mb-4 text-blue-400 shadow-inner">
            <FileVideo className="w-8 h-8" />
          </div>

          <h3 className="text-xl font-bold text-white mb-2">
            Upload Video for <span className="text-blue-400">{currentExerciseObj.name}</span>
          </h3>
          <p className="text-gray-400 text-xs sm:text-sm mb-6 max-w-md">
            MP4, MOV, or WEBM up to 150MB. Side-profile (90°) or oblique (45°) angle recommended for maximum tracking accuracy.
          </p>

          {/* Action Buttons for Mobile & Desktop */}
          <div className="flex flex-col sm:flex-row items-center gap-3 w-full max-w-xs sm:max-w-md justify-center">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={validating}
              className="w-full sm:w-auto bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-6 py-2.5 rounded-xl font-semibold transition-colors shadow-lg shadow-blue-600/20 text-sm flex items-center justify-center gap-2"
            >
              <Upload className="w-4 h-4" />
              <span>Browse Video File</span>
            </button>

            <button
              type="button"
              onClick={() => cameraInputRef.current?.click()}
              disabled={validating}
              className="w-full sm:w-auto bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-200 px-5 py-2.5 rounded-xl font-semibold transition-colors text-sm flex items-center justify-center gap-2"
            >
              <Camera className="w-4 h-4 text-emerald-400" />
              <span>Record on Camera</span>
            </button>
          </div>

          <div className="mt-4 text-[11px] text-gray-500 flex items-center gap-1">
            <span>✨ Automatically detects reps, 3D elbow flare, and velocity loss</span>
          </div>

        </div>
      </div>

      {/* Sticky Mobile Quick Upload / Record Bar */}
      <div className="sm:hidden fixed bottom-16 left-3 right-3 z-30 p-2 bg-gray-900/95 backdrop-blur-xl border border-blue-500/40 rounded-2xl shadow-2xl shadow-black/80 flex items-center gap-2 animate-in slide-in-from-bottom-3 duration-200">
        <button
          type="button"
          onClick={() => cameraInputRef.current?.click()}
          disabled={validating}
          className="flex-1 bg-gradient-to-r from-emerald-600 to-teal-600 active:scale-[0.98] text-white py-2.5 px-3 rounded-xl font-bold text-xs flex items-center justify-center gap-1.5 shadow-md shadow-emerald-900/30"
        >
          <Camera className="w-4 h-4" />
          <span>Record Live</span>
        </button>

        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={validating}
          className="flex-1 bg-blue-600 active:scale-[0.98] text-white py-2.5 px-3 rounded-xl font-bold text-xs flex items-center justify-center gap-1.5 shadow-md shadow-blue-900/30"
        >
          <Upload className="w-4 h-4" />
          <span>Upload File</span>
        </button>
      </div>

      {/* Interactive Video Trimmer Modal */}
      {isTrimmerOpen && pendingFile && (
        <VideoTrimmerModal
          file={pendingFile}
          isOpen={isTrimmerOpen}
          onClose={() => {
            setIsTrimmerOpen(false);
            setPendingFile(null);
          }}
          onConfirmTrim={handleConfirmTrim}
        />
      )}

    </div>
  );
}
