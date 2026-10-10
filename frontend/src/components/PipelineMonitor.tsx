import React, { useEffect, useState } from 'react';
import { Loader2, Server, Brain, Activity, CheckCircle2 } from 'lucide-react';
import { API_BASE_URL } from '../lib/api';

interface PipelineMonitorProps {
  status: string;
  logId: number | null;
  onComplete: (data: any) => void;
  onError: (errMsg?: string) => void;
  onCancel?: () => void;
  accessToken?: string;
  uploadBytes?: number;
}

export default function PipelineMonitor({ status, logId, onComplete, onError, onCancel, accessToken, uploadBytes }: PipelineMonitorProps) {
  const [stage, setStage] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  // Timer counter
  useEffect(() => {
    const timer = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (status === 'uploading') {
      setStage(1);
    } else if (status === 'processing' && logId) {
      setStage(2);
      
      let consecutiveErrors = 0;
      let stopped = false;
      let pollTimeout: number | undefined;
      let completionTimeout: number | undefined;
      let activeController: AbortController | null = null;
      
      const checkStatus = async () => {
        if (stopped) return;
        activeController = new AbortController();
        try {
          const headers: Record<string, string> = {};
          if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
          const res = await fetch(`${API_BASE_URL}/api/v1/results/${logId}`, {
            headers,
            signal: activeController.signal,
          });
          if (!res.ok) {
            consecutiveErrors++;
            if (consecutiveErrors >= 4) {
              stopped = true;
              onError(`Server connection error (${res.status}). The processing worker may have restarted.`);
            }
            return;
          }
          
          consecutiveErrors = 0;
          const data = await res.json();
          
          if (data.status === 'completed' || data.status === 'metrics_ready') {
            stopped = true;
            setStage(5);
            completionTimeout = window.setTimeout(() => onComplete(data), 500);
          } else if (data.status === 'failed') {
            stopped = true;
            onError('Analysis could not extract clear pose landmarks from this video. Please ensure good lighting and clear view of lifter.');
          } else if (data.status === 'processing' || data.status === 'pending') {
            if (data.overlay_video_url) {
              setStage(4); // Rendering Overlay Video
            } else if (data.coach_feedback) {
              setStage(3); // Generating AI Cues
            } else if (data.raw_timeseries_data) {
              setStage(3);
            } else {
              setStage(2); // Extracting Biomechanics
            }
          }
        } catch (err: any) {
          if (err?.name === 'AbortError') return;
          console.error("Polling error:", err);
          consecutiveErrors++;
          if (consecutiveErrors >= 4) {
            stopped = true;
            onError('Connection to analysis server timed out. Please check your network or re-upload.');
          }
        } finally {
          activeController = null;
          if (!stopped) pollTimeout = window.setTimeout(checkStatus, 2000);
        }
      };

      // Schedule the next poll only after the previous request finishes.
      checkStatus();
      
      return () => {
        stopped = true;
        activeController?.abort();
        if (pollTimeout !== undefined) window.clearTimeout(pollTimeout);
        if (completionTimeout !== undefined) window.clearTimeout(completionTimeout);
      };
    }
  }, [status, logId, accessToken, onComplete, onError]);

  const stages = [
    { id: 1, name: 'Uploading Video', desc: 'Sending video file to cloud storage...', icon: Server },
    { id: 2, name: 'Extracting Biomechanics', desc: 'Computing 1€-filtered 3D kinematics and joint angles...', icon: Activity },
    { id: 3, name: 'Generating AI Cues', desc: 'Evaluating form against lower-lat biomechanics rules...', icon: Brain },
    { id: 4, name: 'Rendering Overlay Video', desc: 'Compositing synchronized PIP dashboard & H.264 stream...', icon: Activity }
  ];

  return (
    <div className="bg-gray-900/80 border border-gray-800 rounded-2xl p-6 sm:p-8 shadow-2xl backdrop-blur-sm max-w-2xl mx-auto animate-in fade-in duration-300 relative">
      
      {/* Cancel / Home Button */}
      {onCancel && (
        <button
          onClick={onCancel}
          className="absolute top-4 right-4 text-gray-500 hover:text-gray-300 hover:bg-gray-800/80 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors flex items-center gap-1 border border-transparent hover:border-gray-700"
          title="Cancel and return to home page"
        >
          <span>✕</span>
          <span className="hidden sm:inline">Cancel &amp; Home</span>
        </button>
      )}

      {/* Top Header */}
      <div className="text-center mb-8">
        <div className="inline-flex items-center gap-2 bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-semibold px-3 py-1 rounded-full mb-3">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          <span>Processing Set • {elapsedSeconds}s elapsed</span>
        </div>
        <h3 className="text-2xl font-extrabold text-white">
          {status === 'uploading' ? 'Uploading Your Clip' : 'Analyzing Biomechanics'}
        </h3>
        <p className="text-gray-400 text-xs sm:text-sm mt-1">
          {status === 'uploading'
            ? `Sending ${uploadBytes ? `${(uploadBytes / 1024 / 1024).toFixed(1)} MB of video` : 'your video'} to cloud storage.`
            : 'Running dual-state MediaPipe pose tracker and frame-rate invariant state machine.'}
        </p>
      </div>
      
      {/* Progress Timeline */}
      <div className="relative pl-4 sm:pl-8 space-y-6">
        <div className="absolute left-[31px] sm:left-[47px] top-6 bottom-6 w-0.5 bg-gray-800"></div>

        {stages.map((s) => {
          const isActive = stage === s.id;
          const isDone = stage > s.id;
          const Icon = s.icon;
          
          return (
            <div key={s.id} className={`flex items-start gap-4 sm:gap-6 relative transition-opacity duration-300 ${!isActive && !isDone ? 'opacity-40' : 'opacity-100'}`}>
              
              <div className={`w-10 h-10 sm:w-12 sm:h-12 rounded-xl flex items-center justify-center z-10 border transition-all shrink-0 ${
                isDone 
                  ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-400' 
                  : isActive 
                    ? 'bg-blue-600 border-blue-400 text-white ring-4 ring-blue-500/20 animate-pulse' 
                    : 'bg-gray-800 border-gray-700 text-gray-500'
              }`}>
                {isDone ? (
                  <CheckCircle2 className="w-5 h-5 sm:w-6 sm:h-6" />
                ) : isActive ? (
                  <Loader2 className="w-5 h-5 sm:w-6 sm:h-6 animate-spin" />
                ) : (
                  <Icon className="w-5 h-5 sm:w-6 sm:h-6" />
                )}
              </div>

              <div className="flex-1 pt-1">
                <div className="flex items-center justify-between">
                  <h4 className={`text-sm sm:text-base font-bold ${isActive ? 'text-blue-400' : isDone ? 'text-emerald-400' : 'text-gray-400'}`}>
                    {s.name}
                  </h4>
                  {isDone && (
                    <span className="text-[11px] text-emerald-400 font-semibold uppercase tracking-wider">Done</span>
                  )}
                  {isActive && (
                    <span className="text-[11px] text-blue-400 font-semibold uppercase tracking-wider animate-pulse">Running</span>
                  )}
                </div>
                <p className="text-gray-400 text-xs mt-0.5 leading-relaxed">
                  {isDone ? 'Completed successfully' : isActive ? s.desc : 'Queued'}
                </p>
              </div>

            </div>
          );
        })}
      </div>

      <div className="mt-8 pt-4 border-t border-gray-800 text-center text-xs text-gray-500 flex flex-col items-center gap-3">
        <div>Time depends on connection speed, video length, and backend workload.</div>
        
        {onCancel && (
          <button
            onClick={onCancel}
            className="text-gray-400 hover:text-gray-200 text-xs font-semibold underline underline-offset-4 transition-colors"
          >
            Cancel and Return to Home Page
          </button>
        )}

        {elapsedSeconds > 45 && (
          <div className="w-full p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-300 text-xs flex flex-col sm:flex-row items-center justify-between gap-2 animate-in fade-in">
            <span>Taking longer than expected? You can cancel and try a shorter 5–15s clip.</span>
            <button
              onClick={() => {
                if (onCancel) onCancel();
                else onError("Processing cancelled by user.");
              }}
              className="px-3 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 rounded-lg text-xs font-semibold transition-colors shrink-0"
            >
              Cancel &amp; Return Home
            </button>
          </div>
        )}
      </div>

    </div>
  );
}
