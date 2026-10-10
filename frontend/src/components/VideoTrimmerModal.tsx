import React, { useState, useRef, useEffect } from 'react';
import { Play, Pause, Scissors, Sparkles, Clock, Check, X, RotateCcw } from 'lucide-react';
import type { TrimRange } from '../lib/videoFiles';
import { readVideoDuration } from '../lib/videoMetadata';

interface VideoTrimmerModalProps {
  file: File;
  isOpen: boolean;
  onClose: () => void;
  onConfirmTrim: (file: File, range: TrimRange | null) => void;
}

export default function VideoTrimmerModal({
  file,
  isOpen,
  onClose,
  onConfirmTrim,
}: VideoTrimmerModalProps) {
  const [videoUrl, setVideoUrl] = useState<string>('');
  const [duration, setDuration] = useState<number>(0);
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [trimStart, setTrimStart] = useState<number>(0);
  const [trimEnd, setTrimEnd] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [mediaError, setMediaError] = useState<string | null>(null);

  const [draggingHandle, setDraggingHandle] = useState<'start' | 'end' | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const isSeekingRef = useRef<boolean>(false);
  const pendingSeekTimeRef = useRef<number | null>(null);
  const seekRafIdRef = useRef<number | null>(null);
  const dragCleanupRef = useRef<(() => void) | null>(null);
  const durationReadyRef = useRef(false);
  const metadataFallbackRef = useRef<(() => void) | null>(null);

  const initializeDuration = (dur: number) => {
    if (!Number.isFinite(dur) || dur <= 0 || durationReadyRef.current) return;
    durationReadyRef.current = true;
    setDuration(dur);
    setTrimStart(dur > 15 ? Math.min(2.0, dur * 0.1) : 0);
    setTrimEnd(dur > 15 ? Math.max(dur - 2.0, dur * 0.9) : dur);
  };

  // Generate object URL when file changes
  useEffect(() => {
    if (file) {
      const url = URL.createObjectURL(file);
      setVideoUrl(url);
      setCurrentTime(0);
      setIsPlaying(false);
      setDuration(0);
      setTrimStart(0);
      setTrimEnd(0);
      setMediaError(null);
      durationReadyRef.current = false;
      const metadataController = new AbortController();
      let metadataStarted = false;
      const readMetadata = () => {
        if (durationReadyRef.current || metadataStarted) return;
        metadataStarted = true;
        void readVideoDuration(file, metadataController.signal).then((dur) => {
          if (!metadataController.signal.aborted) initializeDuration(dur);
        }).catch(() => {
          if (!metadataController.signal.aborted && !durationReadyRef.current) {
            setMediaError('This recording could not be previewed or its duration read. You can analyze the entire video or trim it in your phone editor.');
          }
        });
      };
      metadataFallbackRef.current = readMetadata;
      const metadataTimer = setTimeout(readMetadata, 2000);

      return () => {
        clearTimeout(metadataTimer);
        metadataController.abort();
        metadataFallbackRef.current = null;
        dragCleanupRef.current?.();
        if (seekRafIdRef.current !== null) {
          cancelAnimationFrame(seekRafIdRef.current);
          seekRafIdRef.current = null;
        }
        videoRef.current?.pause();
        URL.revokeObjectURL(url);
      };
    }
  }, [file]);

  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      const dur = videoRef.current.duration;
      if (!Number.isFinite(dur) || dur <= 0) {
        metadataFallbackRef.current?.();
        return;
      }
      initializeDuration(dur);
    }
  };

  // Active RAF loop to strictly clamp video playback between [trimStart, trimEnd]
  useEffect(() => {
    let rafId: number;
    const checkPlaybackLoop = () => {
      const vid = videoRef.current;
      if (vid && isPlaying && !draggingHandle) {
        const cur = vid.currentTime;
        if (cur < trimStart - 0.05) {
          vid.currentTime = trimStart;
        } else if (cur >= trimEnd - 0.05) {
          vid.currentTime = trimStart;
        }
        setCurrentTime(vid.currentTime);
      }
      if (isPlaying) {
        rafId = requestAnimationFrame(checkPlaybackLoop);
      }
    };

    if (isPlaying) {
      rafId = requestAnimationFrame(checkPlaybackLoop);
    }
    return () => {
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, [isPlaying, trimStart, trimEnd, draggingHandle]);

  const handleTimeUpdate = () => {
    if (videoRef.current && !draggingHandle && !isPlaying) {
      const cur = videoRef.current.currentTime;
      setCurrentTime(cur);
    }
  };

  const togglePlay = () => {
    if (mediaError) return;
    const vid = videoRef.current;
    if (!vid) return;
    if (isPlaying) {
      vid.pause();
      setIsPlaying(false);
    } else {
      // If currentTime is outside active range or near the end, reset to trimStart
      if (vid.currentTime < trimStart || vid.currentTime >= trimEnd - 0.1) {
        vid.currentTime = trimStart;
        setCurrentTime(trimStart);
      }
      vid.play()
        .then(() => {
          setIsPlaying(true);
        })
        .catch(() => {
          vid.currentTime = trimStart;
          setCurrentTime(trimStart);
          setIsPlaying(false);
        });
    }
  };

  const seekTo = (time: number) => {
    const vid = videoRef.current;
    if (!vid) return;
    const clamped = Math.max(0, Math.min(duration, time));
    setCurrentTime(clamped);
    if (mediaError) return;

    // Smooth RAF-throttled seeking for mobile hardware decoders
    pendingSeekTimeRef.current = clamped;
    if (!isSeekingRef.current) {
      isSeekingRef.current = true;
      seekRafIdRef.current = requestAnimationFrame(() => {
        if (vid && pendingSeekTimeRef.current !== null) {
          try {
            if ('fastSeek' in vid && typeof (vid as any).fastSeek === 'function') {
              (vid as any).fastSeek(pendingSeekTimeRef.current);
            } else {
              vid.currentTime = pendingSeekTimeRef.current;
            }
          } catch {
            vid.currentTime = pendingSeekTimeRef.current;
          }
        }
        isSeekingRef.current = false;
        seekRafIdRef.current = null;
      });
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 10);
    return `${mins}:${secs.toString().padStart(2, '0')}.${ms}`;
  };

  const handleReset = () => {
    setIsPlaying(false);
    if (videoRef.current) videoRef.current.pause();
    setTrimStart(0);
    setTrimEnd(duration);
    seekTo(0);
  };

  const handleStartPointerDown = (e: React.PointerEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsPlaying(false);
    if (videoRef.current) videoRef.current.pause();
    setDraggingHandle('start');

    try {
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    } catch {}

    dragCleanupRef.current?.();

    const onPointerMove = (moveEvent: PointerEvent) => {
      if (!trackRef.current || duration <= 0) return;
      const rect = trackRef.current.getBoundingClientRect();
      if (rect.width <= 0) return;
      const ratio = Math.max(0, Math.min(1, (moveEvent.clientX - rect.left) / rect.width));
      const targetTime = ratio * duration;
      const nextStart = Math.max(0, Math.min(trimEnd - 0.5, targetTime));
      setTrimStart(nextStart);
      seekTo(nextStart);
    };

    const cleanup = () => {
      setDraggingHandle(null);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', cleanup);
      window.removeEventListener('pointercancel', cleanup);
      window.removeEventListener('blur', cleanup);
      dragCleanupRef.current = null;
    };

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', cleanup);
    window.addEventListener('pointercancel', cleanup);
    window.addEventListener('blur', cleanup);
    dragCleanupRef.current = cleanup;
  };

  const handleEndPointerDown = (e: React.PointerEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsPlaying(false);
    if (videoRef.current) videoRef.current.pause();
    setDraggingHandle('end');

    try {
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    } catch {}

    dragCleanupRef.current?.();

    const onPointerMove = (moveEvent: PointerEvent) => {
      if (!trackRef.current || duration <= 0) return;
      const rect = trackRef.current.getBoundingClientRect();
      if (rect.width <= 0) return;
      const ratio = Math.max(0, Math.min(1, (moveEvent.clientX - rect.left) / rect.width));
      const targetTime = ratio * duration;
      const nextEnd = Math.min(duration, Math.max(trimStart + 0.5, targetTime));
      setTrimEnd(nextEnd);
      seekTo(nextEnd);
    };

    const cleanup = () => {
      setDraggingHandle(null);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', cleanup);
      window.removeEventListener('pointercancel', cleanup);
      window.removeEventListener('blur', cleanup);
      dragCleanupRef.current = null;
    };

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', cleanup);
    window.addEventListener('pointercancel', cleanup);
    window.addEventListener('blur', cleanup);
    dragCleanupRef.current = cleanup;
  };

  const handleTrackClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!trackRef.current || duration <= 0) return;
    const rect = trackRef.current.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const clickTime = ratio * duration;

    const distToStart = Math.abs(clickTime - trimStart);
    const distToEnd = Math.abs(clickTime - trimEnd);

    if (distToStart < 1.0) {
      const next = Math.max(0, Math.min(trimEnd - 0.5, clickTime));
      setTrimStart(next);
      seekTo(next);
    } else if (distToEnd < 1.0) {
      const next = Math.min(duration, Math.max(trimStart + 0.5, clickTime));
      setTrimEnd(next);
      seekTo(next);
    } else {
      seekTo(clickTime);
    }
  };

  if (!isOpen) return null;

  const trimmedDuration = Math.max(0, trimEnd - trimStart);
  const timeSaved = Math.max(0, duration - trimmedDuration);
  const hasTrimmed = trimStart > 0.1 || (duration > 0 && trimEnd < duration - 0.1);
  const validRange = Number.isFinite(duration) && duration > 0 && trimStart >= 0 &&
    trimEnd <= duration + 0.001 && trimmedDuration >= 0.5;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="bg-gray-900 border border-gray-800 rounded-3xl max-w-2xl w-full p-6 shadow-2xl space-y-5 overflow-hidden relative">
        
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-gray-800 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400 flex items-center justify-center">
              <Scissors className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-base sm:text-lg font-bold text-white flex items-center gap-2">
                <span>Quick Video Trimmer</span>
                <span className="text-[10px] uppercase font-bold tracking-wider bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded-full border border-emerald-500/20">
                  Optional
                </span>
              </h3>
              <p className="text-xs text-gray-400">
                Choose your exercise range. A new clip will be prepared on your device before uploading.
              </p>
            </div>
          </div>

          <button
            onClick={() => {
              dragCleanupRef.current?.();
              videoRef.current?.pause();
              setIsPlaying(false);
              onClose();
            }}
            className="w-8 h-8 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white flex items-center justify-center transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Video Player Preview */}
        <div className="relative bg-black rounded-2xl overflow-hidden aspect-video border border-gray-800 flex items-center justify-center group">
          <video
            ref={videoRef}
            src={videoUrl}
            onLoadedMetadata={handleLoadedMetadata}
            onError={() => {
              setMediaError('Preview is unavailable in this browser. You can still select the start and end times below.');
              metadataFallbackRef.current?.();
            }}
            onTimeUpdate={handleTimeUpdate}
            onEnded={() => setIsPlaying(false)}
            playsInline
            className="w-full h-full object-contain cursor-pointer"
            onClick={togglePlay}
          />

          {/* Floating Play Overlay */}
          {!draggingHandle && !mediaError && (
            <button
              onClick={togglePlay}
              className={`absolute w-14 h-14 rounded-2xl bg-blue-600/90 text-white flex items-center justify-center shadow-xl backdrop-blur-sm transition-all transform active:scale-95 ${
                isPlaying ? 'opacity-0 group-hover:opacity-80' : 'opacity-100 ring-4 ring-blue-500/30'
              }`}
            >
              {isPlaying ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6 translate-x-0.5" />}
            </button>
          )}

          {/* Current Playhead Time Badge */}
          <div className="absolute top-3 left-3 px-2.5 py-1 bg-black/60 backdrop-blur-md rounded-lg text-white font-mono text-xs border border-white/10">
            {formatTime(currentTime)} / {formatTime(duration)}
          </div>

          {/* Duration Saved Badge */}
          {hasTrimmed && (
            <div className="absolute top-3 right-3 px-2.5 py-1 bg-emerald-950/80 backdrop-blur-md rounded-lg text-emerald-300 font-mono text-xs border border-emerald-500/30 flex items-center gap-1.5 animate-in fade-in">
              <Sparkles className="w-3 h-3 text-emerald-400" />
              <span>Cuts {timeSaved.toFixed(1)}s setup</span>
            </div>
          )}

          {/* Live Mobile Dragging Indicator Banner */}
          {draggingHandle === 'start' && (
            <div className="absolute bottom-4 inset-x-4 mx-auto max-w-xs px-3 py-1.5 bg-blue-600/95 backdrop-blur-md rounded-xl text-white font-mono text-xs text-center shadow-2xl border border-blue-300/60 flex items-center justify-center gap-2 animate-in fade-in">
              <span>🎬 Start of Set:</span>
              <strong className="text-sm font-black">{formatTime(trimStart)}</strong>
            </div>
          )}

          {draggingHandle === 'end' && (
            <div className="absolute bottom-4 inset-x-4 mx-auto max-w-xs px-3 py-1.5 bg-teal-600/95 backdrop-blur-md rounded-xl text-white font-mono text-xs text-center shadow-2xl border border-teal-300/60 flex items-center justify-center gap-2 animate-in fade-in">
              <span>🏁 End of Set:</span>
              <strong className="text-sm font-black">{formatTime(trimEnd)}</strong>
            </div>
          )}
        </div>

        {/* Interactive Trimmer Timeline & Range Handles */}
        <div className="space-y-3 bg-gray-950/60 border border-gray-800/80 p-4 rounded-2xl">
          
          <div className="flex items-center justify-between text-xs text-gray-400">
            <span className="flex items-center gap-1.5 font-medium">
              <Clock className="w-3.5 h-3.5 text-blue-400" />
              <span>Active Set Range:</span>
              <strong className="text-white font-mono">{formatTime(trimStart)} → {formatTime(trimEnd)}</strong>
            </span>
            <span className="font-mono text-emerald-400 font-bold bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
              {trimmedDuration.toFixed(1)}s duration
            </span>
          </div>

          {/* Custom Dual-Handle Scrub Bar */}
          <div className="relative py-4 select-none touch-none">
            
            {/* Track Container */}
            <div
              ref={trackRef}
              onClick={handleTrackClick}
              className="h-7 w-full bg-gray-800/90 rounded-xl overflow-hidden relative cursor-pointer border border-gray-700/60 shadow-inner"
            >
              {/* Active Selected Segment Highlight */}
              {duration > 0 && (
                <div
                  className="absolute top-0 bottom-0 bg-gradient-to-r from-blue-600 to-teal-500 opacity-90 shadow-lg"
                  style={{
                    left: `${(trimStart / duration) * 100}%`,
                    width: `${Math.max(0, ((trimEnd - trimStart) / duration) * 100)}%`,
                  }}
                />
              )}

              {/* Playhead Indicator */}
              {duration > 0 && (
                <div
                  className="absolute top-0 bottom-0 w-0.5 bg-white shadow-lg z-10 pointer-events-none"
                  style={{ left: `${(currentTime / duration) * 100}%` }}
                />
              )}
            </div>

            {/* Left Handle (Trim Start - Blue) */}
            {duration > 0 && (
              <div
                onPointerDown={handleStartPointerDown}
                style={{ left: `calc(${(trimStart / duration) * 100}% - 14px)` }}
                className={`absolute top-1/2 -translate-y-1/2 w-7 h-11 bg-blue-500 hover:bg-blue-400 active:bg-blue-300 text-white rounded-lg shadow-xl shadow-blue-500/50 cursor-ew-resize flex items-center justify-center z-30 transition-transform border-2 border-white group touch-none ${
                  draggingHandle === 'start' ? 'scale-110 ring-4 ring-blue-500/40' : ''
                }`}
                title="Drag to adjust start time"
              >
                {/* Floating Tooltip */}
                <div className="absolute -top-7 left-1/2 -translate-x-1/2 px-1.5 py-0.5 bg-blue-600 text-white rounded text-[10px] font-mono font-bold whitespace-nowrap shadow-md pointer-events-none">
                  {formatTime(trimStart)}
                </div>

                <div className="flex gap-0.5 items-center">
                  <div className="w-0.5 h-4 bg-white rounded-full" />
                  <div className="w-0.5 h-4 bg-white/70 rounded-full" />
                </div>
              </div>
            )}

            {/* Right Handle (Trim End - Teal) */}
            {duration > 0 && (
              <div
                onPointerDown={handleEndPointerDown}
                style={{ left: `calc(${(trimEnd / duration) * 100}% - 14px)` }}
                className={`absolute top-1/2 -translate-y-1/2 w-7 h-11 bg-teal-500 hover:bg-teal-400 active:bg-teal-300 text-white rounded-lg shadow-xl shadow-teal-500/50 cursor-ew-resize flex items-center justify-center z-30 transition-transform border-2 border-white group touch-none ${
                  draggingHandle === 'end' ? 'scale-110 ring-4 ring-teal-500/40' : ''
                }`}
                title="Drag to adjust end time"
              >
                {/* Floating Tooltip */}
                <div className="absolute -top-7 left-1/2 -translate-x-1/2 px-1.5 py-0.5 bg-teal-600 text-white rounded text-[10px] font-mono font-bold whitespace-nowrap shadow-md pointer-events-none">
                  {formatTime(trimEnd)}
                </div>

                <div className="flex gap-0.5 items-center">
                  <div className="w-0.5 h-4 bg-white/70 rounded-full" />
                  <div className="w-0.5 h-4 bg-white rounded-full" />
                </div>
              </div>
            )}

          </div>

          {/* Start & End Nudge Controls */}
          <div className="grid grid-cols-2 gap-3 pt-1">
            <div className="flex items-center justify-between bg-gray-900 border border-gray-800 rounded-xl px-3 py-1.5 text-xs">
              <span className="text-gray-400">Start (Set start):</span>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => {
                    const next = Math.max(0, trimStart - 0.5);
                    setTrimStart(next);
                    seekTo(next);
                  }}
                  className="px-1.5 py-0.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded font-mono font-bold transition-colors"
                >
                  -0.5s
                </button>
                <span className="font-mono text-white font-semibold px-1">{formatTime(trimStart)}</span>
                <button
                  type="button"
                  onClick={() => {
                    const next = Math.min(trimEnd - 0.5, trimStart + 0.5);
                    setTrimStart(next);
                    seekTo(next);
                  }}
                  className="px-1.5 py-0.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded font-mono font-bold transition-colors"
                >
                  +0.5s
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between bg-gray-900 border border-gray-800 rounded-xl px-3 py-1.5 text-xs">
              <span className="text-gray-400">End (Rack/Drop):</span>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => {
                    const next = Math.max(trimStart + 0.5, trimEnd - 0.5);
                    setTrimEnd(next);
                    seekTo(next);
                  }}
                  className="px-1.5 py-0.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded font-mono font-bold transition-colors"
                >
                  -0.5s
                </button>
                <span className="font-mono text-white font-semibold px-1">{formatTime(trimEnd)}</span>
                <button
                  type="button"
                  onClick={() => {
                    const next = Math.min(duration, trimEnd + 0.5);
                    setTrimEnd(next);
                    seekTo(next);
                  }}
                  className="px-1.5 py-0.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded font-mono font-bold transition-colors"
                >
                  +0.5s
                </button>
              </div>
            </div>
          </div>

        </div>

        {mediaError && <p role="alert" className="text-xs text-amber-300">{mediaError}</p>}

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2">
          <button
            type="button"
            onClick={handleReset}
            className="text-xs text-gray-400 hover:text-gray-200 flex items-center gap-1.5 transition-colors order-2 sm:order-1"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Reset to Full Video</span>
          </button>

          <div className="flex items-center gap-2.5 w-full sm:w-auto order-1 sm:order-2 justify-end">
            <button
              type="button"
              onClick={() => {
                dragCleanupRef.current?.();
                videoRef.current?.pause();
                onConfirmTrim(file, null);
              }}
              className="flex-1 sm:flex-none px-4 py-2.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-xl text-xs font-bold transition-colors border border-gray-700 text-center"
            >
              Analyze Entire Video
            </button>

            <button
              type="button"
              disabled={!validRange}
              onClick={() => {
                if (!validRange) return;
                dragCleanupRef.current?.();
                videoRef.current?.pause();
                onConfirmTrim(file, { start: trimStart, end: trimEnd, sourceDuration: duration });
              }}
              className="flex-1 sm:flex-none px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed active:scale-95 text-white rounded-xl text-xs font-bold transition-all shadow-lg shadow-blue-600/30 flex items-center justify-center gap-1.5"
            >
              <Check className="w-4 h-4" />
              <span>Analyze Selected Range</span>
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
