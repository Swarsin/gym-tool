import React, { useState } from 'react';
import { Scale, AlertTriangle, CheckCircle2, ShieldAlert, ArrowRight, Activity, Sparkles } from 'lucide-react';

interface HeatmapRow {
  rep_number: number;
  left_flare_deg: number;
  right_flare_deg: number;
  flare_delta_deg: number;
  dominant_side: string;
  shoulder_tilt_deg: number;
  elevated_side: string;
  status: 'balanced' | 'mild' | 'significant';
  rep_symmetry_score: number;
}

interface AsymmetryAnalysisData {
  overall_symmetry_score: number;
  asymmetry_classification: string;
  avg_flare_delta_deg: number;
  max_flare_delta_deg: number;
  avg_shoulder_tilt_deg: number;
  mean_left_flare_deg: number;
  mean_right_flare_deg: number;
  primary_pattern: string;
  pattern_description: string;
  fatigue_drift_detected: boolean;
  corrective_cues: string[];
  heatmap_rows: HeatmapRow[];
}

interface BilateralImbalanceHeatmapProps {
  asymmetryData?: AsymmetryAnalysisData | null;
  repsData?: any[];
}

export default function BilateralImbalanceHeatmap({
  asymmetryData,
  repsData = []
}: BilateralImbalanceHeatmapProps) {
  const [selectedRep, setSelectedRep] = useState<number | null>(null);

  if (!asymmetryData || !asymmetryData.heatmap_rows || asymmetryData.heatmap_rows.length === 0) {
    return null;
  }

  const {
    overall_symmetry_score = 100,
    asymmetry_classification = 'Symmetrical & Balanced',
    avg_flare_delta_deg = 0,
    max_flare_delta_deg = 0,
    avg_shoulder_tilt_deg = 0,
    mean_left_flare_deg = 70,
    mean_right_flare_deg = 70,
    primary_pattern = 'Balanced Bilateral Mechanics',
    pattern_description = 'Both arms moved with uniform symmetry.',
    fatigue_drift_detected = false,
    corrective_cues = [],
    heatmap_rows = []
  } = asymmetryData;

  const isBalanced = overall_symmetry_score >= 88 && avg_flare_delta_deg <= 5.5;
  const isMild = !isBalanced && (overall_symmetry_score >= 72 || avg_flare_delta_deg <= 12.0);

  const statusTheme = isBalanced
    ? {
        border: 'border-emerald-500/30',
        bgGlow: 'from-emerald-950/30 via-gray-900 to-emerald-950/20',
        scoreColor: 'text-emerald-400',
        badgeBg: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
        icon: CheckCircle2
      }
    : isMild
    ? {
        border: 'border-amber-500/30',
        bgGlow: 'from-amber-950/30 via-gray-900 to-amber-950/20',
        scoreColor: 'text-amber-400',
        badgeBg: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
        icon: AlertTriangle
      }
    : {
        border: 'border-red-500/30',
        bgGlow: 'from-red-950/30 via-gray-900 to-red-950/20',
        scoreColor: 'text-red-400',
        badgeBg: 'bg-red-500/10 border-red-500/30 text-red-400',
        icon: ShieldAlert
      };

  const StatusIcon = statusTheme.icon;

  // Visual balance bar offset (-50% left to +50% right)
  const balanceDifferential = mean_right_flare_deg - mean_left_flare_deg;
  const clampedBalanceBar = Math.max(-100, Math.min(100, balanceDifferential * 5));

  return (
    <div className={`bg-gradient-to-br ${statusTheme.bgGlow} border ${statusTheme.border} rounded-2xl p-5 sm:p-7 shadow-2xl space-y-6 transition-all duration-300`}>
      
      {/* Header & Hero Symmetry Score */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 border-b border-gray-800 pb-5">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Scale className="w-5 h-5 text-indigo-400" />
            <h3 className="text-lg sm:text-xl font-black text-white tracking-tight">
              Bilateral Asymmetry &amp; Imbalance Heatmap
            </h3>
          </div>
          <p className="text-xs sm:text-sm text-gray-400">
            Real-time left vs. right arm elbow flare differential and shoulder elevation stability
          </p>
        </div>

        <div className="flex items-center gap-3 w-full md:w-auto justify-between md:justify-end">
          {fatigue_drift_detected && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-semibold animate-pulse">
              <Activity className="w-3.5 h-3.5 shrink-0" />
              <span>Fatigue Drift Detected</span>
            </div>
          )}

          <div className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full border text-xs font-bold ${statusTheme.badgeBg}`}>
            <StatusIcon className="w-4 h-4 shrink-0" />
            <span>{asymmetry_classification}</span>
          </div>
        </div>
      </div>

      {/* Hero Overview Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        
        {/* Metric 1: Symmetry Score Gauge */}
        <div className="bg-gray-800/80 p-5 rounded-xl border border-gray-700/60 flex flex-col items-center justify-center text-center relative overflow-hidden">
          <div className="text-xs text-gray-400 uppercase tracking-wider font-semibold">
            Overall Symmetry Score
          </div>
          <div className={`text-5xl font-black mt-2 font-mono ${statusTheme.scoreColor}`}>
            {overall_symmetry_score}
            <span className="text-xl text-gray-500 font-normal">%</span>
          </div>
          <div className="text-[11px] text-gray-400 mt-2">
            {overall_symmetry_score >= 88
              ? 'Optimal mechanical balance'
              : overall_symmetry_score >= 72
              ? 'Minor dominant-side bias'
              : 'Compensatory hitching present'}
          </div>
        </div>

        {/* Metric 2: Mean Flare Differential */}
        <div className="bg-gray-800/80 p-5 rounded-xl border border-gray-700/60 flex flex-col justify-between">
          <div>
            <div className="text-xs text-gray-400 uppercase tracking-wider font-semibold flex items-center justify-between">
              <span>Elbow Flare Delta (Δ)</span>
              <span className="text-xs font-mono text-gray-300">Max: {max_flare_delta_deg}°</span>
            </div>
            <div className="text-3xl font-black text-white mt-1.5 font-mono">
              {avg_flare_delta_deg.toFixed(1)}°
              <span className="text-xs text-gray-500 font-normal ml-1">avg difference</span>
            </div>
          </div>

          {/* Visual Balance Slider */}
          <div className="mt-3 space-y-1">
            <div className="flex justify-between text-[10px] text-gray-400 uppercase font-semibold">
              <span className="text-emerald-400">Left Bias</span>
              <span>Center (0°)</span>
              <span className="text-cyan-400">Right Bias</span>
            </div>
            <div className="h-2 w-full bg-gray-900 rounded-full relative overflow-hidden border border-gray-700">
              <div
                className={`absolute top-0 bottom-0 w-3 rounded-full transition-all duration-500 ${
                  Math.abs(clampedBalanceBar) < 15
                    ? 'bg-emerald-400'
                    : Math.abs(clampedBalanceBar) < 40
                    ? 'bg-amber-400'
                    : 'bg-red-400'
                }`}
                style={{
                  left: `calc(50% + ${clampedBalanceBar / 2}% - 6px)`
                }}
              />
            </div>
          </div>
        </div>

        {/* Metric 3: Shoulder Elevation / Tilt */}
        <div className="bg-gray-800/80 p-5 rounded-xl border border-gray-700/60 flex flex-col justify-between">
          <div>
            <div className="text-xs text-gray-400 uppercase tracking-wider font-semibold">
              Peak Shoulder Tilt / Hitching
            </div>
            <div className="text-3xl font-black text-white mt-1.5 font-mono">
              {avg_shoulder_tilt_deg.toFixed(1)}°
              <span className="text-xs text-gray-500 font-normal ml-1">scapular elevation</span>
            </div>
          </div>
          <div className="text-[11px] text-gray-400 mt-2">
            {avg_shoulder_tilt_deg <= 3.0
              ? 'Symmetrical scapular depression'
              : 'Unilateral upper trap shrugging detected'}
          </div>
        </div>

      </div>

      {/* Side-by-Side Arm Comparison Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        
        {/* Left Arm Card */}
        <div className="bg-emerald-950/20 border border-emerald-500/20 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between border-b border-emerald-500/10 pb-2">
            <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider">
              Left Arm Kinematics
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 font-medium">
              Left Flare Baseline
            </span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-gray-400">Mean Concentric Flare:</span>
            <span className="text-xl font-bold text-emerald-300 font-mono">
              {mean_left_flare_deg.toFixed(1)}°
            </span>
          </div>
          <div className="w-full bg-gray-800 rounded-full h-1.5 overflow-hidden">
            <div
              className="bg-emerald-400 h-full rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, (mean_left_flare_deg / 90) * 100)}%` }}
            />
          </div>
        </div>

        {/* Right Arm Card */}
        <div className="bg-cyan-950/20 border border-cyan-500/20 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between border-b border-cyan-500/10 pb-2">
            <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider">
              Right Arm Kinematics
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 font-medium">
              Right Flare Baseline
            </span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-gray-400">Mean Concentric Flare:</span>
            <span className="text-xl font-bold text-cyan-300 font-mono">
              {mean_right_flare_deg.toFixed(1)}°
            </span>
          </div>
          <div className="w-full bg-gray-800 rounded-full h-1.5 overflow-hidden">
            <div
              className="bg-cyan-400 h-full rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, (mean_right_flare_deg / 90) * 100)}%` }}
            />
          </div>
        </div>

      </div>

      {/* Rep-by-Rep Heatmap Matrix Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs uppercase tracking-wider font-bold text-gray-300 flex items-center gap-2">
            <Activity className="w-4 h-4 text-purple-400" />
            Rep-by-Rep Heatmap Matrix
          </h4>
          <span className="text-[11px] text-gray-400">
            Click a row to highlight rep
          </span>
        </div>

        {/* Desktop Heatmap Table (>= md) */}
        <div className="hidden md:block overflow-x-auto rounded-xl border border-gray-700/80 bg-gray-900/80">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-gray-700 text-gray-400 uppercase tracking-wider text-[11px] bg-gray-800/60">
                <th className="py-2.5 px-4 font-bold">Rep</th>
                <th className="py-2.5 px-4 font-bold">Left Flare</th>
                <th className="py-2.5 px-4 font-bold">Right Flare</th>
                <th className="py-2.5 px-4 font-bold">Delta (Δ)</th>
                <th className="py-2.5 px-4 font-bold">Shoulder Tilt</th>
                <th className="py-2.5 px-4 font-bold">Balance Status</th>
                <th className="py-2.5 px-4 font-bold text-right">Rep Symmetry</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {heatmap_rows.map((row) => {
                const isSelected = selectedRep === row.rep_number;
                const statusBadge =
                  row.status === 'balanced' ? (
                    <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-semibold text-[10px]">
                      Balanced
                    </span>
                  ) : row.status === 'mild' ? (
                    <span className="px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 font-semibold text-[10px]">
                      Mild Asym ({row.dominant_side})
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded-full bg-red-500/10 text-red-400 border border-red-500/20 font-semibold text-[10px]">
                      Imbalanced ({row.dominant_side})
                    </span>
                  );

                const deltaHeatColor =
                  row.flare_delta_deg <= 5.0
                    ? 'text-emerald-400'
                    : row.flare_delta_deg <= 12.0
                    ? 'text-amber-400'
                    : 'text-red-400 font-bold';

                return (
                  <tr
                    key={row.rep_number}
                    onClick={() => setSelectedRep(isSelected ? null : row.rep_number)}
                    className={`cursor-pointer transition-colors ${
                      isSelected ? 'bg-indigo-950/40 border-l-2 border-indigo-400' : 'hover:bg-gray-800/40'
                    }`}
                  >
                    <td className="py-3 px-4 font-bold text-white font-mono">#{row.rep_number}</td>
                    <td className="py-3 px-4 text-emerald-300 font-mono font-medium">
                      {row.left_flare_deg.toFixed(1)}°
                    </td>
                    <td className="py-3 px-4 text-cyan-300 font-mono font-medium">
                      {row.right_flare_deg.toFixed(1)}°
                    </td>
                    <td className={`py-3 px-4 font-mono ${deltaHeatColor}`}>
                      {row.flare_delta_deg.toFixed(1)}°
                      {row.dominant_side !== 'Balanced' && (
                        <span className="text-[10px] text-gray-500 ml-1">({row.dominant_side[0]})</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-gray-300 font-mono">
                      {row.shoulder_tilt_deg.toFixed(1)}°
                      {row.elevated_side !== 'Balanced' && (
                        <span className="text-[10px] text-gray-500 ml-1">({row.elevated_side[0]})</span>
                      )}
                    </td>
                    <td className="py-3 px-4">{statusBadge}</td>
                    <td className="py-3 px-4 text-right font-mono font-bold text-white">
                      {row.rep_symmetry_score}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Mobile Heatmap Cards (< md) */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 md:hidden">
          {heatmap_rows.map((row) => (
            <div
              key={row.rep_number}
              onClick={() => setSelectedRep(selectedRep === row.rep_number ? null : row.rep_number)}
              className={`p-3.5 rounded-xl border transition-all ${
                row.status === 'balanced'
                  ? 'bg-gray-900/80 border-emerald-500/20'
                  : row.status === 'mild'
                  ? 'bg-gray-900/80 border-amber-500/20'
                  : 'bg-gray-900/80 border-red-500/20'
              }`}
            >
              <div className="flex items-center justify-between border-b border-gray-800 pb-2 mb-2">
                <span className="font-extrabold text-white text-xs">Rep #{row.rep_number}</span>
                <span className="font-mono text-xs font-bold text-white">{row.rep_symmetry_score}% Sym</span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                <div className="bg-gray-800/60 p-2 rounded-lg">
                  <span className="text-[10px] text-gray-400 block font-sans">Left Flare</span>
                  <span className="text-emerald-300 font-bold">{row.left_flare_deg.toFixed(1)}°</span>
                </div>
                <div className="bg-gray-800/60 p-2 rounded-lg">
                  <span className="text-[10px] text-gray-400 block font-sans">Right Flare</span>
                  <span className="text-cyan-300 font-bold">{row.right_flare_deg.toFixed(1)}°</span>
                </div>
                <div className="bg-gray-800/60 p-2 rounded-lg">
                  <span className="text-[10px] text-gray-400 block font-sans">Flare Delta (Δ)</span>
                  <span className={`font-bold ${row.flare_delta_deg > 10 ? 'text-red-400' : 'text-amber-400'}`}>
                    {row.flare_delta_deg.toFixed(1)}° ({row.dominant_side})
                  </span>
                </div>
                <div className="bg-gray-800/60 p-2 rounded-lg">
                  <span className="text-[10px] text-gray-400 block font-sans">Shoulder Tilt</span>
                  <span className="text-gray-200">{row.shoulder_tilt_deg.toFixed(1)}°</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Pattern Diagnostic & Actionable Corrective Protocol */}
      <div className="bg-gray-800/70 border border-gray-700/60 rounded-xl p-5 space-y-3">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider font-bold text-gray-300">
          <Sparkles className="w-4 h-4 text-indigo-400" />
          <span>Biomechanical Diagnostic: {primary_pattern}</span>
        </div>
        <p className="text-xs sm:text-sm text-gray-300 leading-relaxed">
          {pattern_description}
        </p>

        {corrective_cues.length > 0 && (
          <div className="pt-2 border-t border-gray-700/50 space-y-2">
            <span className="text-[11px] uppercase tracking-wider font-bold text-gray-400 block">
              Targeted Corrective Protocol:
            </span>
            <ul className="space-y-1.5">
              {corrective_cues.map((cue, idx) => (
                <li key={idx} className="flex items-start gap-2 text-xs text-gray-300">
                  <ArrowRight className="w-3.5 h-3.5 text-indigo-400 shrink-0 mt-0.5" />
                  <span>{cue}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

    </div>
  );
}
