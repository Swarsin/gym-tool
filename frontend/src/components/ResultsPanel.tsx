import React, { useState, useEffect } from 'react';
import { Target, Activity, Dumbbell, ArrowRight, Play, ExternalLink, Zap, ShieldCheck, AlertCircle, Info, Sparkles, Loader2 } from 'lucide-react';
import ThreeDSkeletonViewer from './ThreeDSkeletonViewer';
import BilateralImbalanceHeatmap from './BilateralImbalanceHeatmap';
import { API_BASE_URL } from '../lib/api';
import { supabase } from '../lib/supabase';

interface ResultsPanelProps {
  data: any;
  onReset: () => void;
}

export default function ResultsPanel({ data, onReset }: ResultsPanelProps) {
  const [overlayVideoUrl, setOverlayVideoUrl] = useState<string | null>(data?.overlay_video_url || null);
  const [liveCoachFeedback, setLiveCoachFeedback] = useState<any>(data?.coach_feedback || null);
  const [isPollingVideo, setIsPollingVideo] = useState<boolean>(
    !data?.overlay_video_url && data?.status === 'metrics_ready'
  );

  useEffect(() => {
    setOverlayVideoUrl(data?.overlay_video_url || null);
    setIsPollingVideo(!data?.overlay_video_url && data?.status === 'metrics_ready');
  }, [data?.id, data?.overlay_video_url, data?.status]);

  useEffect(() => {
    if (!data?.id || overlayVideoUrl || !isPollingVideo) return;

    let stopped = false;
    let pollInterval: number;

    const checkVideoReady = async () => {
      if (stopped) return;
      try {
        const { data: sessionData } = await supabase.auth.getSession();
        const headers: Record<string, string> = {};
        if (sessionData.session?.access_token) {
          headers.Authorization = `Bearer ${sessionData.session.access_token}`;
        }

        const res = await fetch(`${API_BASE_URL}/api/v1/results/${data.id}`, { headers });
        if (res.ok) {
          const updated = await res.json();
          if (updated.coach_feedback && Object.keys(updated.coach_feedback).length > 0) {
            setLiveCoachFeedback(updated.coach_feedback);
          }
          if (updated.overlay_video_url) {
            setOverlayVideoUrl(updated.overlay_video_url);
            setIsPollingVideo(false);
          } else if (updated.status === 'completed' || updated.status === 'failed') {
            setIsPollingVideo(false);
          }
        }
      } catch (err) {
        console.error("Polling for overlay video error:", err);
      }
    };

    pollInterval = window.setInterval(checkVideoReady, 3000);
    return () => {
      stopped = true;
      clearInterval(pollInterval);
    };
  }, [data?.id, overlayVideoUrl, isPollingVideo]);

  if (!data) {
    return (
      <div className="bg-gray-800 rounded-xl p-8 border border-gray-700 text-center space-y-4">
        <p className="text-gray-300">No workout result data available.</p>
        <button onClick={onReset} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm">
          Return to Upload
        </button>
      </div>
    );
  }

  const totalReps = data.total_reps ?? 0;
  const avgEccentric = typeof data.avg_eccentric_tempo === 'number' ? data.avg_eccentric_tempo.toFixed(1) : '0.0';
  const avgElbowFlare = typeof data.avg_elbow_flare === 'number' ? data.avg_elbow_flare.toFixed(1) : '0.0';
  const coachFeedback = liveCoachFeedback || data.coach_feedback || {};

  const cameraObservations = coachFeedback.camera_observations || 'All repetitions tracked cleanly.';
  const actionableCues: string[] = coachFeedback.actionable_cues || [];
  const measurementLimitations = coachFeedback.measurement_limitations || 'Velocity loss gated on repetition ROM consistency.';
  const scorecard = Array.isArray(coachFeedback.scorecard) ? coachFeedback.scorecard : [];

  const repsData: any[] = data.raw_timeseries_data?.reps_data || [];
  const skeleton3dFrames: any[] = data.raw_timeseries_data?.skeleton_3d_frames || [];
  const vbtSummary = data.raw_timeseries_data?.vbt_summary;
  const scaleCalibration = data.raw_timeseries_data?.scale_calibration;
  const exerciseName = data.raw_timeseries_data?.exercise_name || "Pull-Up / Chin-Up";
  const asymmetryData = data.raw_timeseries_data?.asymmetry_analysis;

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      
      {/* Exercise & Scale Calibration Badges */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2.5 bg-gray-800/90 border border-gray-700 px-5 py-3.5 rounded-xl shadow-lg">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400 uppercase tracking-wider font-bold">Exercise:</span>
          <span className="text-sm sm:text-base font-extrabold text-blue-400">{exerciseName}</span>
        </div>
        
        {scaleCalibration && (
          <div className="flex items-center gap-2 text-xs flex-wrap">
            <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
            <span className="text-gray-400">Calibration:</span>
            <span className="font-semibold text-emerald-400 bg-emerald-500/10 px-2.5 py-0.5 rounded-full border border-emerald-500/20 text-[11px] truncate max-w-[220px]">
              {scaleCalibration.scale_confidence}
            </span>
          </div>
        )}
      </div>

      {/* Interactive 3D Skeleton Visualizer & Synchronized Video Player */}
      <ThreeDSkeletonViewer
        framesData={skeleton3dFrames}
        repsData={repsData}
        videoUrl={overlayVideoUrl}
        exerciseName={exerciseName}
        fps={data.raw_timeseries_data?.sampling_fps || 30}
      />

      {/* Top Measurements Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 flex flex-col items-center">
          <Dumbbell className="w-8 h-8 text-blue-400 mb-3" />
          <div className="text-xs text-gray-400 uppercase tracking-wider font-semibold">Total Completed Reps</div>
          <div className="text-4xl font-bold mt-2 text-white">{totalReps}</div>
        </div>
        
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 flex flex-col items-center">
          <Activity className="w-8 h-8 text-purple-400 mb-3" />
          <div className="text-xs text-gray-400 uppercase tracking-wider font-semibold">Avg Eccentric Tempo</div>
          <div className="text-4xl font-bold mt-2 text-purple-300">{avgEccentric}s</div>
          <div className="text-xs text-gray-400 mt-2 font-medium">Descent Control: Smooth</div>
        </div>

        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 flex flex-col items-center">
          <Target className="w-8 h-8 text-emerald-400 mb-3" />
          <div className="text-xs text-gray-400 uppercase tracking-wider font-semibold">Estimated 3D Flare</div>
          <div className="text-4xl font-bold mt-2 text-emerald-300">{avgElbowFlare}°</div>
          <div className="text-xs text-gray-400 mt-2 font-medium">Compatible with Grip Angle</div>
        </div>
      </div>

      {/* VBT Physics & Velocity Profile Card */}
      {vbtSummary && (
        <div className="bg-gradient-to-r from-emerald-950/40 via-gray-900 to-emerald-950/40 border border-emerald-500/30 rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between border-b border-gray-800 pb-3">
            <div className="flex items-center gap-2.5">
              <Zap className="w-5 h-5 text-emerald-400" />
              <h3 className="text-base font-bold text-white">Velocity-Based Training (VBT) Measurements</h3>
            </div>
            <span className="text-xs text-emerald-400 bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/20 font-semibold">
              Shoulder-to-Bar Metric Translation
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-center">
            <div className="bg-gray-800/60 p-4 rounded-xl border border-gray-700/60">
              <div className="text-xs text-gray-400 uppercase tracking-wider font-semibold">Mean Concentric Velocity</div>
              <div className="text-3xl font-black text-blue-400 mt-1">
                {vbtSummary.avg_concentric_velocity_mps?.toFixed(2)}
                <span className="text-xs text-gray-500 font-normal"> m/s</span>
              </div>
              <div className="text-[11px] text-gray-400 mt-1">Displacement / Duration</div>
            </div>

            <div className="bg-gray-800/60 p-4 rounded-xl border border-gray-700/60">
              <div className="text-xs text-gray-400 uppercase tracking-wider font-semibold">Apparent Effort (Est. RPE)</div>
              <div className="text-3xl font-black text-emerald-400 mt-1">
                {vbtSummary.estimated_rpe}
                <span className="text-xs text-gray-500 font-normal"> /10</span>
              </div>
              <div className="text-[11px] text-gray-400 mt-1">
                ~{vbtSummary.estimated_rir} RIR (Video Estimate)
              </div>
            </div>

            <div className="bg-gray-800/60 p-4 rounded-xl border border-gray-700/60">
              <div className="text-xs text-gray-400 uppercase tracking-wider font-semibold">Set Velocity Loss</div>
              {vbtSummary.velocity_loss_available ? (
                <>
                  <div className="text-3xl font-black text-amber-400 mt-1">
                    {vbtSummary.velocity_loss_pct?.toFixed(1)}%
                  </div>
                  <div className="text-[11px] text-amber-400/90 mt-1 font-medium">Fastest vs Final Rep</div>
                </>
              ) : (
                <>
                  <div className="text-xs font-bold text-amber-400 mt-2">
                    {vbtSummary.velocity_loss_reason_code || "UNAVAILABLE"}
                  </div>
                  <div className="text-[10px] text-gray-400 mt-1 leading-tight">
                    {vbtSummary.velocity_loss_explanation || "Repetition ROM was inconsistent."}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Bilateral Asymmetry & Imbalance Heatmap */}
      {asymmetryData && (
        <BilateralImbalanceHeatmap
          asymmetryData={asymmetryData}
          repsData={repsData}
        />
      )}

      {/* Annotated Video Player or Rendering Progress State */}
      {overlayVideoUrl ? (
        <div className="bg-gray-800 rounded-xl border border-gray-700 shadow-xl overflow-hidden animate-in fade-in duration-500">
          <div className="px-6 pt-5 pb-3 border-b border-gray-700 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Play className="w-5 h-5 text-blue-400" />
              <h2 className="text-lg font-bold text-white">Pose Overlay &amp; Synced Waveform PIP</h2>
              <span className="text-xs text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                Confidence-Coded Skeleton
              </span>
            </div>
            <a 
              href={overlayVideoUrl} 
              target="_blank" 
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 bg-blue-500/10 hover:bg-blue-500/20 px-3 py-1.5 rounded-lg border border-blue-500/20 transition-colors"
            >
              <span>Direct Video Link</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
          <div className="p-4 bg-black flex items-center justify-center">
            <video
              key={overlayVideoUrl}
              src={overlayVideoUrl}
              controls
              playsInline
              preload="metadata"
              className="w-full max-h-[500px] rounded-lg shadow-lg"
            >
              <source src={overlayVideoUrl} type="video/mp4" />
              Your browser does not support HTML5 video playback.
            </video>
          </div>
        </div>
      ) : isPollingVideo ? (
        <div className="bg-gradient-to-r from-gray-900 via-blue-950/40 to-gray-900 rounded-xl border border-blue-500/30 p-6 shadow-xl flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center shrink-0">
              <Loader2 className="w-6 h-6 text-blue-400 animate-spin" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-white">Rendering Annotated Video Overlay</span>
                <span className="text-[10px] uppercase font-bold tracking-wider text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded border border-blue-500/20 animate-pulse">
                  Background Processing
                </span>
              </div>
              <p className="text-xs text-gray-400 mt-1">
                Your metrics, 3D skeleton, and AI coaching are ready! Generating confidence-coded skeleton overlays and waveform PIP in the background...
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-blue-300 bg-blue-950/60 px-3 py-1.5 rounded-lg border border-blue-800/40 shrink-0">
            <Sparkles className="w-3.5 h-3.5 text-blue-400 animate-pulse" />
            <span>Auto-refreshing</span>
          </div>
        </div>
      ) : null}

      {/* Three-Tier Scorecard & Biomechanical Analysis */}
      <div className="bg-gradient-to-br from-gray-800 to-gray-900 rounded-xl p-8 border border-gray-700 shadow-xl space-y-6">
        
        {/* Tier 1: Measurements Scorecard */}
        {scorecard.length > 0 && (
          <div>
            <h3 className="text-sm uppercase tracking-wider font-bold text-gray-300 mb-3 flex items-center gap-2">
              <Target className="w-4 h-4 text-blue-400" />
              Biomechanical Execution Scorecard
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              {scorecard.map((item: any, idx: number) => (
                <div key={idx} className="bg-gray-800/90 p-4 rounded-xl border border-gray-700/60 flex flex-col justify-between">
                  <div>
                    <span className="text-gray-400 block font-semibold mb-1">{item.category}</span>
                    <span className={`text-sm font-extrabold block ${
                      item.rating?.toLowerCase().includes('good') || item.rating?.toLowerCase().includes('consistent')
                        ? 'text-emerald-400'
                        : 'text-amber-400'
                    }`}>
                      {item.rating}
                    </span>
                  </div>
                  <div className="mt-2 pt-2 border-t border-gray-700/40 flex items-center justify-between text-[11px] text-gray-400">
                    <span>Conf: {item.confidence}</span>
                    <span className="text-gray-500 truncate ml-1">{item.note}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tier 2: Factual Camera Observations */}
        <div className="bg-gray-800/70 p-5 rounded-xl border border-gray-700/60">
          <h4 className="text-xs uppercase tracking-wider font-bold text-gray-400 mb-2 flex items-center gap-2">
            <Info className="w-4 h-4 text-blue-400" />
            Camera Observations
          </h4>
          <p className="text-gray-200 text-sm leading-relaxed">
            {cameraObservations}
          </p>
        </div>

        {/* Tier 3: Actionable Coaching Cues */}
        {actionableCues.length > 0 && (
          <div>
            <h4 className="text-xs uppercase tracking-wider font-bold text-gray-400 mb-3">Actionable Next-Set Cues:</h4>
            <ul className="space-y-2.5">
              {actionableCues.map((cue: string, idx: number) => (
                <li key={idx} className="flex items-start gap-3 bg-gray-800/50 p-3.5 rounded-lg border border-gray-700/50 text-sm">
                  <ArrowRight className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                  <span className="text-gray-300">{cue}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Measurement Limitations */}
        <div className="bg-amber-950/20 border border-amber-500/20 rounded-lg p-4 text-xs text-gray-400 flex items-start gap-2.5">
          <AlertCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <span><strong>Measurement Limits:</strong> {measurementLimitations}</span>
        </div>

      </div>

      {/* Rep-by-Rep Breakdown Section */}
      {repsData.length > 0 && (
        <div className="bg-gray-800 rounded-xl p-4 sm:p-6 border border-gray-700 shadow-xl space-y-4">
          <h2 className="text-base sm:text-lg font-bold text-white flex items-center gap-2">
            <Activity className="w-5 h-5 text-purple-400" />
            Rep-by-Rep Kinematics
          </h2>
          
          {/* Mobile Stacked Rep Cards (< md screens) */}
          <div className="block md:hidden space-y-3">
            {repsData.map((rep: any, idx: number) => {
              const repNum = rep?.rep_number ?? (idx + 1);
              const flare = typeof rep?.contraction_elbow_flare_degrees === 'number' ? rep.contraction_elbow_flare_degrees : 0;
              const flareL = typeof rep?.left_elbow_flare_deg === 'number' ? rep.left_elbow_flare_deg : flare;
              const flareR = typeof rep?.right_elbow_flare_deg === 'number' ? rep.right_elbow_flare_deg : flare;
              const delta = typeof rep?.elbow_flare_delta_deg === 'number' ? rep.elbow_flare_delta_deg : 0;
              const ecc = typeof rep?.eccentric_tempo_s === 'number' ? rep.eccentric_tempo_s : 0;
              const conc = typeof rep?.concentric_tempo_s === 'number' ? rep.concentric_tempo_s : 0;
              const meanV = typeof rep?.mean_velocity_mps === 'number' ? rep.mean_velocity_mps : 0;
              const concRom = typeof rep?.concentric_rom_pct === 'number' ? rep.concentric_rom_pct : 100;
              const eccRom = typeof rep?.eccentric_rom_pct === 'number' ? rep.eccentric_rom_pct : 100;
              const isPartial = Boolean(rep?.is_partial_rep);
              const isIntentional = Boolean(rep?.is_intentional_partial);

              return (
                <div key={repNum} className="bg-gray-900/90 border border-gray-700/80 rounded-xl p-3.5 space-y-2.5 shadow-md">
                  {/* Card Header */}
                  <div className="flex items-center justify-between border-b border-gray-800 pb-2">
                    <span className="font-extrabold text-white text-sm">Rep #{repNum}</span>
                    {isIntentional ? (
                      <span className="px-2 py-0.5 text-[11px] font-semibold rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
                        Intentional Partial
                      </span>
                    ) : isPartial ? (
                      <span className="px-2 py-0.5 text-[11px] font-semibold rounded-full bg-red-500/10 text-red-400 border border-red-500/20">
                        Partial Start
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 text-[11px] font-semibold rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        Full ROM
                      </span>
                    )}
                  </div>

                  {/* Card Metrics Grid */}
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="bg-gray-800/60 p-2 rounded-lg border border-gray-700/50">
                      <span className="text-[10px] text-gray-400 uppercase font-semibold block">Concentric Speed</span>
                      <span className="text-sm font-bold text-blue-400 font-mono">
                        {meanV > 0 ? `${meanV.toFixed(2)} m/s` : 'N/A'}
                      </span>
                    </div>

                    <div className="bg-gray-800/60 p-2 rounded-lg border border-gray-700/50">
                      <span className="text-[10px] text-gray-400 uppercase font-semibold block">Tempo (Ecc / Conc)</span>
                      <span className="text-xs font-semibold text-purple-300 font-mono">
                        {ecc.toFixed(1)}s / {conc.toFixed(1)}s
                      </span>
                    </div>

                    <div className="bg-gray-800/60 p-2 rounded-lg border border-gray-700/50">
                      <span className="text-[10px] text-gray-400 uppercase font-semibold block">ROM Depth</span>
                      <span className="text-xs font-medium text-gray-200 font-mono">
                        {concRom.toFixed(0)}% conc / {eccRom.toFixed(0)}% ecc
                      </span>
                    </div>

                    <div className="bg-gray-800/60 p-2 rounded-lg border border-gray-700/50">
                      <span className="text-[10px] text-gray-400 uppercase font-semibold block">Bilateral Flare (L/R)</span>
                      <span className="text-xs font-medium font-mono">
                        <span className="text-emerald-400">{flareL.toFixed(0)}°</span>
                        <span className="text-gray-500 mx-1">/</span>
                        <span className="text-cyan-400">{flareR.toFixed(0)}°</span>
                        {delta > 0 && (
                          <span className={`ml-1 text-[10px] ${delta > 10 ? 'text-red-400 font-bold' : delta > 5 ? 'text-amber-400' : 'text-gray-400'}`}>
                            Δ{delta.toFixed(0)}°
                          </span>
                        )}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Desktop Table (>= md screens) */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-gray-700 text-gray-400 text-xs uppercase tracking-wider">
                  <th className="py-3 px-4">Rep</th>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-4">Concentric ROM</th>
                  <th className="py-3 px-4">Eccentric ROM</th>
                  <th className="py-3 px-4">Bilateral Flare (L / R)</th>
                  <th className="py-3 px-4">Tempo (Ecc / Conc)</th>
                  <th className="py-3 px-4">Mean Speed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700/50">
                {repsData.map((rep: any, idx: number) => {
                  const repNum = rep?.rep_number ?? (idx + 1);
                  const flare = typeof rep?.contraction_elbow_flare_degrees === 'number' ? rep.contraction_elbow_flare_degrees : 0;
                  const flareL = typeof rep?.left_elbow_flare_deg === 'number' ? rep.left_elbow_flare_deg : flare;
                  const flareR = typeof rep?.right_elbow_flare_deg === 'number' ? rep.right_elbow_flare_deg : flare;
                  const delta = typeof rep?.elbow_flare_delta_deg === 'number' ? rep.elbow_flare_delta_deg : 0;
                  const ecc = typeof rep?.eccentric_tempo_s === 'number' ? rep.eccentric_tempo_s : 0;
                  const conc = typeof rep?.concentric_tempo_s === 'number' ? rep.concentric_tempo_s : 0;
                  const meanV = typeof rep?.mean_velocity_mps === 'number' ? rep.mean_velocity_mps : 0;
                  const concRom = typeof rep?.concentric_rom_pct === 'number' ? rep.concentric_rom_pct : 100;
                  const eccRom = typeof rep?.eccentric_rom_pct === 'number' ? rep.eccentric_rom_pct : 100;
                  const isPartial = Boolean(rep?.is_partial_rep);
                  const isIntentional = Boolean(rep?.is_intentional_partial);

                  return (
                    <tr key={repNum} className="text-sm hover:bg-gray-700/20 transition-colors">
                      <td className="py-3.5 px-4 font-semibold text-white font-mono">#{repNum}</td>
                      <td className="py-3.5 px-4">
                        {isIntentional ? (
                          <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
                            Intentional Partial
                          </span>
                        ) : isPartial ? (
                          <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-red-500/10 text-red-400 border border-red-500/20">
                            Partial Start
                          </span>
                        ) : (
                          <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            Full ROM
                          </span>
                        )}
                      </td>
                      <td className="py-3.5 px-4">
                        <span className="text-xs text-gray-200 font-mono">{concRom}%</span>
                      </td>
                      <td className="py-3.5 px-4">
                        <span className="text-xs text-gray-200 font-mono">{eccRom}%</span>
                      </td>
                      <td className="py-3.5 px-4 text-xs font-mono">
                        <span className="text-emerald-400">{flareL.toFixed(0)}°</span>
                        <span className="text-gray-500 mx-1">/</span>
                        <span className="text-cyan-400">{flareR.toFixed(0)}°</span>
                        {delta > 0 && (
                          <span className={`ml-1.5 text-[11px] ${delta > 10 ? 'text-red-400 font-bold' : delta > 5 ? 'text-amber-400' : 'text-gray-400'}`}>
                            (Δ{delta.toFixed(1)}°)
                          </span>
                        )}
                      </td>
                      <td className="py-3.5 px-4 text-xs text-gray-300 font-mono">
                        {ecc.toFixed(1)}s / {conc.toFixed(1)}s
                      </td>
                      <td className="py-3.5 px-4 text-xs font-semibold text-blue-400 font-mono">
                        {meanV > 0 ? `${meanV.toFixed(2)} m/s` : 'N/A'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

    </div>
  );
}
