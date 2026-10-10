import React, { useState, useEffect } from 'react';
import {
  TrendingUp,
  Zap,
  Clock,
  Target,
  BarChart3,
  Calendar,
  Activity,
  Sparkles,
  Info,
  ChevronRight,
  Flame,
  Filter,
  RefreshCw,
  Play
} from 'lucide-react';
import { API_BASE_URL } from '../lib/api';
import { EXERCISES } from './UploadZone';

export interface TrendDataPoint {
  log_id: number;
  workout_id: number;
  date: string;
  timestamp: string;
  exercise_name: string;
  total_reps: number;
  mean_concentric_velocity: number;
  peak_concentric_velocity: number;
  velocity_loss_pct?: number | null;
  avg_eccentric_tempo: number;
  avg_elbow_flare: number;
  rom_consistency_pct: number;
  estimated_rpe?: number | null;
  overlay_video_url?: string | null;
}

export interface OverloadDelta {
  velocity_delta_pct: number;
  fastest_rep_delta_pct: number;
  tempo_stability_pct: number;
  rom_standardization_score: number;
  total_volume_reps: number;
  sessions_analyzed: number;
  adaptation_status: string;
}

export interface TrendsResponse {
  time_range: string;
  exercise_filter: string;
  data_points: TrendDataPoint[];
  overload_delta: OverloadDelta;
  macro_ai_insight: string;
}

type MetricMode = 'velocity' | 'peak_velocity' | 'tempo' | 'velocity_loss' | 'rom';
type TimeRange = '7d' | '30d' | '90d' | 'all';

interface TrendAnalyticsProps {
  userId?: string;
  accessToken?: string;
  onSelectLog: (logId: number) => void;
}

export default function TrendAnalytics({ userId, accessToken, onSelectLog }: TrendAnalyticsProps) {
  const [trends, setTrends] = useState<TrendsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedExercise, setSelectedExercise] = useState<string>('all');
  const [selectedTimeRange, setSelectedTimeRange] = useState<TimeRange>('all');
  const [metricMode, setMetricMode] = useState<MetricMode>('velocity');
  const [hoveredPoint, setHoveredPoint] = useState<TrendDataPoint | null>(null);
  const [hoverPosition, setHoverPosition] = useState<{ x: number; y: number } | null>(null);

  const fetchTrends = async () => {
    if (!accessToken) {
      setLoading(false);
      setTrends(null);
      return;
    }
    setLoading(true);
    try {
      const headers: Record<string, string> = {
        'Authorization': `Bearer ${accessToken}`,
      };

      const params = new URLSearchParams();
      if (userId) params.append('user_id', userId);
      if (selectedExercise !== 'all') params.append('exercise', selectedExercise);
      if (selectedTimeRange !== 'all') params.append('time_range', selectedTimeRange);

      const url = `${API_BASE_URL}/api/v1/analytics/trends?${params.toString()}`;
      const res = await fetch(url, { headers });
      if (res.ok) {
        const data = await res.json();
        setTrends(data);
      }
    } catch (err) {
      console.error('Failed to fetch trend analytics:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrends();
  }, [userId, accessToken, selectedExercise, selectedTimeRange]);

  const dataPoints = trends?.data_points || [];
  const overloadDelta = trends?.overload_delta;

  // Metric configuration
  const metricConfigs = {
    velocity: {
      label: 'Mean Velocity',
      unit: 'm/s',
      color: '#3b82f6', // blue
      gradient: 'from-blue-500/20 to-blue-500/0',
      getValue: (d: TrendDataPoint) => d.mean_concentric_velocity,
      format: (v: number) => `${v.toFixed(2)} m/s`,
      description: 'Concentric drive speed (neuromuscular force output)',
    },
    peak_velocity: {
      label: 'Peak Velocity',
      unit: 'm/s',
      color: '#06b6d4', // cyan
      gradient: 'from-cyan-500/20 to-cyan-500/0',
      getValue: (d: TrendDataPoint) => d.peak_concentric_velocity,
      format: (v: number) => `${v.toFixed(2)} m/s`,
      description: 'Fastest single rep speed in the set',
    },
    tempo: {
      label: 'Eccentric Tempo',
      unit: 's',
      color: '#a855f7', // purple
      gradient: 'from-purple-500/20 to-purple-500/0',
      getValue: (d: TrendDataPoint) => d.avg_eccentric_tempo,
      format: (v: number) => `${v.toFixed(1)}s`,
      description: 'Descent time per rep (eccentric hypertrophy control)',
    },
    velocity_loss: {
      label: 'Velocity Loss',
      unit: '%',
      color: '#f59e0b', // amber
      gradient: 'from-amber-500/20 to-amber-500/0',
      getValue: (d: TrendDataPoint) => d.velocity_loss_pct ?? 0,
      format: (v: number) => `${v.toFixed(1)}%`,
      description: 'Intra-set fatigue (first rep vs final rep)',
    },
    rom: {
      label: 'ROM Consistency',
      unit: '%',
      color: '#10b981', // emerald
      gradient: 'from-emerald-500/20 to-emerald-500/0',
      getValue: (d: TrendDataPoint) => d.rom_consistency_pct,
      format: (v: number) => `${v.toFixed(1)}%`,
      description: 'Full-extension standardization across reps',
    },
  };

  const currentCfg = metricConfigs[metricMode];

  // SVG Chart Geometry
  const svgWidth = 800;
  const svgHeight = 260;
  const padding = { top: 25, right: 30, bottom: 40, left: 55 };
  const chartW = svgWidth - padding.left - padding.right;
  const chartH = svgHeight - padding.top - padding.bottom;

  // Compute Scales
  const values = dataPoints.map(currentCfg.getValue);
  const minVal = values.length > 0 ? Math.min(...values) : 0;
  const maxVal = values.length > 0 ? Math.max(...values) : 1;
  const yPadding = (maxVal - minVal) * 0.15 || 0.1;
  const yMin = Math.max(0, minVal - yPadding);
  const yMax = maxVal + yPadding;

  const getX = (idx: number) => {
    if (dataPoints.length <= 1) return padding.left + chartW / 2;
    return padding.left + (idx / (dataPoints.length - 1)) * chartW;
  };

  const getY = (val: number) => {
    if (yMax === yMin) return padding.top + chartH / 2;
    return padding.top + chartH - ((val - yMin) / (yMax - yMin)) * chartH;
  };

  // Generate SVG path for line and area fill
  const linePoints = dataPoints.map((d, i) => `${getX(i)},${getY(currentCfg.getValue(d))}`).join(' ');
  const areaPath = dataPoints.length > 0
    ? `M ${getX(0)},${padding.top + chartH} L ${dataPoints.map((d, i) => `${getX(i)},${getY(currentCfg.getValue(d))}`).join(' L ')} L ${getX(dataPoints.length - 1)},${padding.top + chartH} Z`
    : '';

  // Generate Y-axis grid ticks (4 ticks)
  const yTicks = [0, 0.33, 0.66, 1].map((pct) => {
    const val = yMin + pct * (yMax - yMin);
    return {
      val,
      y: getY(val),
      label: currentCfg.format(val),
    };
  });

  return (
    <div className="space-y-6">
      
      {/* 1. Header & Metric Mode Tabs */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 shadow-xl space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-gray-800 pb-5">
          <div>
            <div className="flex items-center gap-2.5 text-blue-400 font-bold text-xs uppercase tracking-wider">
              <TrendingUp className="w-4 h-4" />
              <span>Tier 2 Performance Engine</span>
            </div>
            <h2 className="text-xl sm:text-2xl font-black text-white mt-1">
              Progressive Overload &amp; VBT Trends
            </h2>
            <p className="text-xs text-gray-400 mt-1">
              {currentCfg.description} across your logged training sessions
            </p>
          </div>

          {/* Time Range & Refresh */}
          <div className="flex items-center gap-2">
            <div className="flex bg-gray-800 p-1 rounded-xl border border-gray-700">
              {(['7d', '30d', '90d', 'all'] as TimeRange[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setSelectedTimeRange(t)}
                  className={`px-3 py-1 text-xs font-semibold rounded-lg transition-colors ${
                    selectedTimeRange === t
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'text-gray-400 hover:text-white'
                  }`}
                >
                  {t === 'all' ? 'All Time' : t.toUpperCase()}
                </button>
              ))}
            </div>

            <button
              onClick={fetchTrends}
              disabled={loading}
              className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-xl transition-colors border border-gray-800"
              title="Refresh trends"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-blue-400' : ''}`} />
            </button>
          </div>
        </div>

        {/* Metric Selector Pills & Exercise Filter */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="flex flex-wrap gap-2">
            {(Object.keys(metricConfigs) as MetricMode[]).map((key) => {
              const cfg = metricConfigs[key];
              const isActive = metricMode === key;
              return (
                <button
                  key={key}
                  onClick={() => setMetricMode(key)}
                  className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all border ${
                    isActive
                      ? 'bg-gray-800 text-white border-blue-500 shadow-md shadow-blue-500/10'
                      : 'bg-gray-900/60 text-gray-400 border-gray-800 hover:border-gray-700 hover:text-gray-200'
                  }`}
                >
                  <span
                    className="w-2.5 h-2.5 rounded-full"
                    style={{ backgroundColor: cfg.color }}
                  />
                  <span>{cfg.label}</span>
                </button>
              );
            })}
          </div>

          {/* Exercise Filter Dropdown */}
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-500" />
            <select
              value={selectedExercise}
              onChange={(e) => setSelectedExercise(e.target.value)}
              className="bg-gray-800 border border-gray-700 text-gray-200 text-xs rounded-xl px-3 py-2 font-medium focus:outline-none focus:border-blue-500"
            >
              <option value="all">All Exercises</option>
              {EXERCISES.map((e) => (
                <option key={e.id} value={e.name}>
                  {e.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* 2. Interactive SVG Chart */}
        <div className="relative bg-black/40 rounded-xl border border-gray-800/80 p-3 sm:p-4 overflow-hidden">
          {loading ? (
            <div className="h-48 sm:h-64 flex flex-col items-center justify-center text-gray-400 gap-3">
              <RefreshCw className="w-6 h-6 animate-spin text-blue-400" />
              <span className="text-xs font-medium">Computing longitudinal kinematics...</span>
            </div>
          ) : dataPoints.length === 0 ? (
            <div className="h-48 sm:h-64 flex flex-col items-center justify-center text-gray-500 gap-2">
              <Activity className="w-8 h-8 text-gray-600" />
              <span className="text-sm font-semibold text-gray-400">
                {!accessToken ? 'Sign in to view performance trends' : 'No workout data found for this filter'}
              </span>
              <span className="text-xs text-gray-500 text-center max-w-sm">
                {!accessToken
                  ? 'Sign in above to track your personal velocity-based training curves and form trends.'
                  : 'Record or upload sets to start generating trend curves.'}
              </span>
            </div>
          ) : (
            <div className="relative w-full">
              <svg
                viewBox={`0 0 ${svgWidth} ${svgHeight}`}
                className="w-full h-48 sm:h-64 select-none"
                onMouseLeave={() => {
                  setHoveredPoint(null);
                  setHoverPosition(null);
                }}
              >
                <defs>
                  <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={currentCfg.color} stopOpacity="0.35" />
                    <stop offset="100%" stopColor={currentCfg.color} stopOpacity="0.0" />
                  </linearGradient>
                </defs>

                {/* Y-Axis Grid Lines & Labels */}
                {yTicks.map((tick, idx) => (
                  <g key={idx}>
                    <line
                      x1={padding.left}
                      y1={tick.y}
                      x2={svgWidth - padding.right}
                      y2={tick.y}
                      stroke="#374151"
                      strokeDasharray="4 4"
                      strokeOpacity="0.4"
                    />
                    <text
                      x={padding.left - 8}
                      y={tick.y + 4}
                      textAnchor="end"
                      fontSize="10"
                      fill="#9ca3af"
                      fontFamily="sans-serif"
                    >
                      {tick.label}
                    </text>
                  </g>
                ))}

                {/* Area Gradient Fill */}
                <path d={areaPath} fill="url(#chartGradient)" />

                {/* Main Curve Line */}
                <polyline
                  fill="none"
                  stroke={currentCfg.color}
                  strokeWidth="3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  points={linePoints}
                />

                {/* Data Points */}
                {dataPoints.map((d, i) => {
                  const x = getX(i);
                  const y = getY(currentCfg.getValue(d));
                  const isHovered = hoveredPoint?.log_id === d.log_id;
                  const showPoint = isHovered || dataPoints.length <= 15 || i % Math.ceil(dataPoints.length / 12) === 0 || i === dataPoints.length - 1;

                  return (
                    <g key={d.log_id} className="cursor-pointer">
                      {/* Vertical Hover Guide */}
                      {isHovered && (
                        <line
                          x1={x}
                          y1={padding.top}
                          x2={x}
                          y2={padding.top + chartH}
                          stroke="#6b7280"
                          strokeDasharray="3 3"
                          strokeWidth="1.5"
                        />
                      )}

                      {/* Visible Point Dot */}
                      {showPoint && (
                        <circle
                          cx={x}
                          y={y}
                          r={isHovered ? 7 : 3.5}
                          fill={isHovered ? currentCfg.color : '#111827'}
                          stroke={currentCfg.color}
                          strokeWidth={isHovered ? 3 : 2}
                          className="transition-all duration-150"
                        />
                      )}

                      {/* Click/Hover Hitbox */}
                      <circle
                        cx={x}
                        y={y}
                        r="18"
                        fill="transparent"
                        onMouseEnter={(e) => {
                          setHoveredPoint(d);
                          const rect = e.currentTarget.getBoundingClientRect();
                          setHoverPosition({ x: rect.left, y: rect.top });
                        }}
                        onClick={() => onSelectLog(d.log_id)}
                      />

                      {/* X-Axis Date Labels */}
                      {(i === 0 || i === dataPoints.length - 1 || i % Math.ceil(dataPoints.length / 5) === 0) && (
                        <text
                          x={x}
                          y={svgHeight - 10}
                          textAnchor="middle"
                          fontSize="9"
                          fill="#9ca3af"
                          fontFamily="sans-serif"
                        >
                          {d.date.split(',')[0]}
                        </text>
                      )}
                    </g>
                  );
                })}
              </svg>

              {/* Hover Tooltip Card */}
              {hoveredPoint && (
                <div
                  className="absolute z-20 bg-gray-900/95 backdrop-blur-md border border-gray-700 text-white rounded-xl p-3 shadow-2xl pointer-events-auto transition-all animate-in fade-in zoom-in-95 duration-150 text-xs space-y-1.5 min-w-[190px] max-w-[calc(100vw-2.5rem)]"
                  style={{
                    left: `${Math.min(svgWidth - 210, Math.max(10, getX(dataPoints.findIndex(p => p.log_id === hoveredPoint.log_id)) - 95))}px`,
                    top: '8px',
                  }}
                >
                  <div className="flex items-center justify-between border-b border-gray-800 pb-1">
                    <span className="font-bold text-gray-200 truncate">{hoveredPoint.exercise_name}</span>
                    <span className="text-[10px] text-gray-400">{hoveredPoint.date}</span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 pt-0.5">
                    <div>
                      <span className="text-[10px] text-gray-400 block">{currentCfg.label}</span>
                      <span className="text-sm font-black" style={{ color: currentCfg.color }}>
                        {currentCfg.format(currentCfg.getValue(hoveredPoint))}
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-gray-400 block">Total Volume</span>
                      <span className="text-sm font-bold text-white">{hoveredPoint.total_reps} reps</span>
                    </div>
                    <div>
                      <span className="text-[10px] text-gray-400 block">Tempo</span>
                      <span className="text-xs font-medium text-purple-300">{hoveredPoint.avg_eccentric_tempo}s ecc</span>
                    </div>
                    <div>
                      <span className="text-[10px] text-gray-400 block">ROM</span>
                      <span className="text-xs font-medium text-emerald-300">{hoveredPoint.rom_consistency_pct}%</span>
                    </div>
                  </div>

                  <button
                    onClick={() => onSelectLog(hoveredPoint.log_id)}
                    className="w-full mt-1.5 flex items-center justify-center gap-1.5 py-1.5 bg-blue-600/30 hover:bg-blue-600 text-blue-300 hover:text-white rounded-lg font-bold text-[11px] transition-colors border border-blue-500/30"
                  >
                    <Play className="w-3 h-3" />
                    <span>View Set Analysis</span>
                    <ChevronRight className="w-3 h-3" />
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 3. Progressive Overload KPI Summary Matrix */}
      {overloadDelta && overloadDelta.sessions_analyzed > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          
          {/* Velocity Delta */}
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 shadow-lg relative overflow-hidden flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <div className="p-2.5 bg-blue-500/10 rounded-xl text-blue-400 border border-blue-500/20">
                <Zap className="w-5 h-5" />
              </div>
              <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${
                overloadDelta.velocity_delta_pct >= 0
                  ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                  : 'text-amber-400 bg-amber-500/10 border-amber-500/20'
              }`}>
                {overloadDelta.velocity_delta_pct >= 0 ? '+' : ''}{overloadDelta.velocity_delta_pct}%
              </span>
            </div>
            <div className="mt-4">
              <div className="text-xs text-gray-400 uppercase tracking-wider font-semibold">Neuromuscular Drive</div>
              <div className="text-xl font-black text-white mt-1">
                {overloadDelta.velocity_delta_pct >= 0 ? 'Force Gained' : 'Load Progression'}
              </div>
              <div className="text-[11px] text-gray-400 mt-1 truncate">{overloadDelta.adaptation_status}</div>
            </div>
          </div>

          {/* Peak Speed Delta */}
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 shadow-lg relative overflow-hidden flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <div className="p-2.5 bg-cyan-500/10 rounded-xl text-cyan-400 border border-cyan-500/20">
                <Flame className="w-5 h-5" />
              </div>
              <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${
                overloadDelta.fastest_rep_delta_pct >= 0
                  ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                  : 'text-amber-400 bg-amber-500/10 border-amber-500/20'
              }`}>
                {overloadDelta.fastest_rep_delta_pct >= 0 ? '+' : ''}{overloadDelta.fastest_rep_delta_pct}%
              </span>
            </div>
            <div className="mt-4">
              <div className="text-xs text-gray-400 uppercase tracking-wider font-semibold">Fastest Rep Power</div>
              <div className="text-xl font-black text-white mt-1">Peak Speed Delta</div>
              <div className="text-[11px] text-gray-400 mt-1">Max instantaneous velocity</div>
            </div>
          </div>

          {/* Tempo Stability */}
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 shadow-lg relative overflow-hidden flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <div className="p-2.5 bg-purple-500/10 rounded-xl text-purple-400 border border-purple-500/20">
                <Clock className="w-5 h-5" />
              </div>
              <span className="text-xs font-bold text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded-full border border-purple-500/20">
                {overloadDelta.tempo_stability_pct}% Stable
              </span>
            </div>
            <div className="mt-4">
              <div className="text-xs text-gray-400 uppercase tracking-wider font-semibold">Tempo Discipline</div>
              <div className="text-xl font-black text-white mt-1">Descent Control</div>
              <div className="text-[11px] text-gray-400 mt-1">Eccentric pacing stability</div>
            </div>
          </div>

          {/* ROM Standardization */}
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 shadow-lg relative overflow-hidden flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <div className="p-2.5 bg-emerald-500/10 rounded-xl text-emerald-400 border border-emerald-500/20">
                <Target className="w-5 h-5" />
              </div>
              <span className="text-xs font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                {overloadDelta.rom_standardization_score}% ROM
              </span>
            </div>
            <div className="mt-4">
              <div className="text-xs text-gray-400 uppercase tracking-wider font-semibold">Standardization</div>
              <div className="text-xl font-black text-white mt-1">Depth Consistency</div>
              <div className="text-[11px] text-gray-400 mt-1">{overloadDelta.total_volume_reps} total reps audited</div>
            </div>
          </div>

        </div>
      )}

      {/* 4. AI Macro Progression Coach Insights Banner */}
      {trends?.macro_ai_insight && (
        <div className="bg-gradient-to-r from-blue-950/40 via-purple-950/30 to-blue-950/40 border border-blue-500/30 rounded-2xl p-6 shadow-xl flex items-start gap-4">
          <div className="p-3 bg-blue-500/20 rounded-2xl text-blue-400 border border-blue-500/30 shrink-0">
            <Sparkles className="w-6 h-6" />
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-black uppercase tracking-wider text-blue-300">
                Cross-Session Adaptation Analysis
              </h3>
              <span className="text-[10px] font-bold bg-blue-500/20 text-blue-300 px-2 py-0.5 rounded-full border border-blue-500/30">
                AI Coach
              </span>
            </div>
            <p className="text-sm text-gray-200 leading-relaxed">
              {trends.macro_ai_insight}
            </p>
          </div>
        </div>
      )}

    </div>
  );
}
