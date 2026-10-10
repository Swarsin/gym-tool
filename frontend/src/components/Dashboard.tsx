import React, { useEffect, useState } from 'react';
import {
  Dumbbell,
  Calendar,
  Play,
  Trash2,
  RefreshCw,
  Plus,
  Flame,
  Clock,
  Target,
  BarChart3,
  TrendingUp,
  Search,
  Filter,
  CheckCircle2,
  AlertCircle
} from 'lucide-react';
import { EXERCISES } from './UploadZone';
import { API_BASE_URL } from '../lib/api';
import TrendAnalytics from './TrendAnalytics';

export interface HistoryItem {
  log_id: number;
  workout_id: number;
  exercise_name: string;
  created_at: string;
  status: string;
  total_reps: number;
  avg_eccentric_tempo: number;
  avg_elbow_flare: number;
  overall_score?: number;
  primary_flaw?: string;
  overlay_video_url?: string;
}

export interface DashboardStats {
  total_workouts: number;
  total_reps: number;
  avg_eccentric_tempo: number;
  avg_elbow_flare: number;
  avg_score?: number;
  completed_count: number;
}

interface DashboardProps {
  userId?: string;
  accessToken?: string;
  onSelectLog: (logId: number) => void;
  onNewUpload: () => void;
  onShowToast: (toast: { type: 'success' | 'error' | 'info' | 'warning'; title: string; message?: string }) => void;
}

export default function Dashboard({
  userId,
  accessToken,
  onSelectLog,
  onNewUpload,
  onShowToast,
}: DashboardProps) {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedExercise, setSelectedExercise] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [dashboardView, setDashboardView] = useState<'trends' | 'history'>('trends');

  const fetchDashboardData = async () => {
    if (!accessToken) {
      setLoading(false);
      setHistory([]);
      setStats(null);
      return;
    }

    setLoading(true);
    try {
      const headers: Record<string, string> = {
        'Authorization': `Bearer ${accessToken}`,
      };

      // 1. Fetch History
      let histUrl = `${API_BASE_URL}/api/v1/history`;
      const params = new URLSearchParams();
      if (selectedExercise !== 'all') params.append('exercise', selectedExercise);
      if (params.toString()) histUrl += `?${params.toString()}`;

      const histRes = await fetch(histUrl, { headers });
      if (histRes.ok) {
        const histData = await histRes.json();
        setHistory(histData);
      }

      // 2. Fetch Stats
      const statsRes = await fetch(`${API_BASE_URL}/api/v1/stats`, { headers });
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
      }
    } catch (err: any) {
      console.warn('Failed to load dashboard data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, [userId, accessToken, selectedExercise]);

  const handleDelete = async (e: React.MouseEvent, workoutId: number, logId: number) => {
    e.stopPropagation();
    if (!window.confirm('Are you sure you want to delete this workout log?')) return;

    try {
      setDeletingId(workoutId);
      const headers: Record<string, string> = {};
      if (accessToken) {
        headers['Authorization'] = `Bearer ${accessToken}`;
      }

      const res = await fetch(`${API_BASE_URL}/api/v1/workout/${workoutId}`, {
        method: 'DELETE',
        headers,
      });

      if (!res.ok) {
        throw new Error('Failed to delete workout');
      }

      setHistory((prev) => prev.filter((item) => item.workout_id !== workoutId));
      onShowToast({
        type: 'success',
        title: 'Workout Deleted',
        message: 'Session has been removed from your history.',
      });
      // Refresh stats
      fetchDashboardData();
    } catch (err: any) {
      console.error('Delete error:', err);
      onShowToast({
        type: 'error',
        title: 'Delete Failed',
        message: err.message || 'Could not delete workout.',
      });
    } finally {
      setDeletingId(null);
    }
  };

  const formatDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  const getScoreBadge = (score?: number) => {
    if (score === undefined || score === null) return null;
    if (score >= 8) {
      return (
        <span className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-lg text-xs font-bold">
          {score}/10 High
        </span>
      );
    }
    if (score >= 6) {
      return (
        <span className="bg-amber-500/10 text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded-lg text-xs font-bold">
          {score}/10 Fair
        </span>
      );
    }
    return (
      <span className="bg-red-500/10 text-red-400 border border-red-500/30 px-2 py-0.5 rounded-lg text-xs font-bold">
        {score}/10 Needs Work
      </span>
    );
  };

  const filteredHistory = history.filter((item) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      item.exercise_name.toLowerCase().includes(q) ||
      (item.primary_flaw && item.primary_flaw.toLowerCase().includes(q))
    );
  });

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      
      {/* Top Header & Quick Action */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-gray-900/60 border border-gray-800 p-6 rounded-2xl shadow-xl backdrop-blur-sm">
        <div>
          <div className="flex items-center gap-2.5">
            <BarChart3 className="w-6 h-6 text-blue-400" />
            <h2 className="text-2xl font-bold text-white tracking-tight">Performance &amp; Form Dashboard</h2>
          </div>
          <p className="text-gray-400 text-xs sm:text-sm mt-1">
            Track your movement quality, velocity adaptation, and progressive overload across all sets.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchDashboardData}
            title="Refresh dashboard"
            className="p-2.5 bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white border border-gray-700 rounded-xl transition-colors shadow-sm"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={onNewUpload}
            className="flex items-center gap-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white px-4 py-2.5 rounded-xl font-semibold text-sm transition-all shadow-lg shadow-blue-600/20"
          >
            <Plus className="w-4 h-4" />
            <span>Analyze New Video</span>
          </button>
        </div>
      </div>

      {/* Sub-View Switcher Tabs */}
      <div className="flex bg-gray-900/90 p-1.5 rounded-2xl border border-gray-800 w-full sm:w-auto self-start shadow-md">
        <button
          onClick={() => setDashboardView('trends')}
          className={`flex-1 sm:flex-none flex items-center justify-center gap-2 px-3 sm:px-4 py-2 rounded-xl text-xs font-bold transition-all ${
            dashboardView === 'trends'
              ? 'bg-blue-600 text-white shadow-md shadow-blue-600/20'
              : 'text-gray-400 hover:text-white hover:bg-gray-800/50'
          }`}
        >
          <TrendingUp className="w-4 h-4 shrink-0" />
          <span className="hidden sm:inline">Progressive Overload Trends</span>
          <span className="sm:hidden">Overload Trends</span>
        </button>
        <button
          onClick={() => setDashboardView('history')}
          className={`flex-1 sm:flex-none flex items-center justify-center gap-2 px-3 sm:px-4 py-2 rounded-xl text-xs font-bold transition-all ${
            dashboardView === 'history'
              ? 'bg-blue-600 text-white shadow-md shadow-blue-600/20'
              : 'text-gray-400 hover:text-white hover:bg-gray-800/50'
          }`}
        >
          <BarChart3 className="w-4 h-4 shrink-0" />
          <span className="hidden sm:inline">Workout Log History ({history.length})</span>
          <span className="sm:hidden">Log History ({history.length})</span>
        </button>
      </div>

      {/* View 1: Progressive Overload & VBT Trend Analytics */}
      {dashboardView === 'trends' && (
        <TrendAnalytics
          userId={userId}
          accessToken={accessToken}
          onSelectLog={onSelectLog}
        />
      )}

      {/* View 2: KPI Overview & Detailed History */}
      {dashboardView === 'history' && (
        <>
          {/* KPI Stats Cards */}
          {stats && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              
              <div className="bg-gray-900/80 border border-gray-800 rounded-2xl p-5 shadow-lg relative overflow-hidden">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">Total Workouts</span>
                  <div className="w-8 h-8 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
                    <Dumbbell className="w-4 h-4" />
                  </div>
                </div>
                <div className="mt-3">
                  <span className="text-2xl sm:text-3xl font-extrabold text-white font-mono">{stats.total_workouts}</span>
                  <span className="text-xs text-gray-500 ml-2">({stats.completed_count} analyzed)</span>
                </div>
                <div className="text-[11px] text-gray-400 mt-1">Recorded biomechanics sets</div>
              </div>

              <div className="bg-gray-900/80 border border-gray-800 rounded-2xl p-5 shadow-lg relative overflow-hidden">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">Total Reps Tracked</span>
                  <div className="w-8 h-8 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                    <Flame className="w-4 h-4" />
                  </div>
                </div>
                <div className="mt-3">
                  <span className="text-2xl sm:text-3xl font-extrabold text-emerald-400 font-mono">{stats.total_reps}</span>
                  <span className="text-xs text-gray-500 ml-2">reps</span>
                </div>
                <div className="text-[11px] text-gray-400 mt-1">Validated concentric/eccentric reps</div>
              </div>

              <div className="bg-gray-900/80 border border-gray-800 rounded-2xl p-5 shadow-lg relative overflow-hidden">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">Avg Elbow Flare</span>
                  <div className="w-8 h-8 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                    <Target className="w-4 h-4" />
                  </div>
                </div>
                <div className="mt-3">
                  <span className="text-2xl sm:text-3xl font-extrabold text-indigo-400 font-mono">{stats.avg_elbow_flare}°</span>
                  <span className="text-xs text-gray-500 ml-2">adduction</span>
                </div>
                <div className="text-[11px] text-gray-400 mt-1">Lower-lat goal: &lt; 25° – 30°</div>
              </div>

              <div className="bg-gray-900/80 border border-gray-800 rounded-2xl p-5 shadow-lg relative overflow-hidden">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">Avg Eccentric Tempo</span>
                  <div className="w-8 h-8 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
                    <Clock className="w-4 h-4" />
                  </div>
                </div>
                <div className="mt-3">
                  <span className="text-2xl sm:text-3xl font-extrabold text-amber-400 font-mono">{stats.avg_eccentric_tempo}s</span>
                  <span className="text-xs text-gray-500 ml-2">/ rep</span>
                </div>
                <div className="text-[11px] text-gray-400 mt-1">Controlled eccentric target: 2.0s–3.0s</div>
              </div>

            </div>
          )}

          {/* Filter & Search Bar */}
          <div className="bg-gray-900/60 border border-gray-800 p-4 rounded-2xl flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-lg">
            
            {/* Exercise Filter Chips */}
            <div className="flex items-center gap-2 overflow-x-auto pb-1 md:pb-0 scrollbar-thin">
              <button
                onClick={() => setSelectedExercise('all')}
                className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all shrink-0 ${
                  selectedExercise === 'all'
                    ? 'bg-blue-600 text-white shadow-md shadow-blue-600/20'
                    : 'bg-gray-800 text-gray-300 hover:bg-gray-700 border border-gray-700'
                }`}
              >
                All Exercises
              </button>
              {EXERCISES.map((ex) => (
                <button
                  key={ex.id}
                  onClick={() => setSelectedExercise(ex.name)}
                  className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all shrink-0 flex items-center gap-1.5 ${
                    selectedExercise === ex.name
                      ? 'bg-blue-600 text-white shadow-md shadow-blue-600/20'
                      : 'bg-gray-800 text-gray-300 hover:bg-gray-700 border border-gray-700'
                  }`}
                >
                  <span>{ex.icon}</span>
                  <span>{ex.name}</span>
                </button>
              ))}
            </div>

            {/* Search Box */}
            <div className="relative min-w-[220px]">
              <Search className="w-4 h-4 text-gray-500 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search by exercise or flaw..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>

          </div>

      {/* Sessions Grid */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-white flex items-center gap-2">
            <span>Session History</span>
            <span className="text-xs bg-gray-800 text-gray-400 px-2.5 py-0.5 rounded-full border border-gray-700 font-mono">
              {filteredHistory.length}
            </span>
          </h3>
        </div>

        {loading && (
          <div className="text-center py-16 bg-gray-900/40 border border-gray-800 rounded-2xl">
            <RefreshCw className="w-8 h-8 animate-spin text-blue-400 mx-auto mb-3" />
            <p className="text-gray-400 text-sm">Loading workout history...</p>
          </div>
        )}

        {!loading && filteredHistory.length === 0 && (
          <div className="text-center py-16 bg-gray-900/40 border border-gray-800 rounded-2xl p-8 space-y-4">
            <div className="w-16 h-16 rounded-2xl bg-gray-800/80 border border-gray-700 flex items-center justify-center mx-auto text-gray-600">
              <Dumbbell className="w-8 h-8" />
            </div>
            <div>
              <h4 className="text-lg font-bold text-white">
                {!accessToken ? 'Sign In to View Workout History' : 'No Workout Sessions Found'}
              </h4>
              <p className="text-gray-400 text-sm max-w-md mx-auto mt-1">
                {!accessToken
                  ? 'Sign in using the button above to view your personal workout history, kinematics breakdowns, and progressive overload metrics.'
                  : searchQuery || selectedExercise !== 'all'
                  ? 'No past recordings match your active filters. Try clearing the filter or search.'
                  : 'You have not uploaded any exercise videos yet. Record your first set to unlock biomechanics analysis.'}
              </p>
            </div>
            {accessToken && (
              <button
                onClick={onNewUpload}
                className="mt-2 inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-5 py-2.5 rounded-xl font-semibold text-sm transition-colors shadow-lg shadow-blue-600/20"
              >
                <Plus className="w-4 h-4" />
                <span>Upload First Workout Video</span>
              </button>
            )}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {!loading &&
            filteredHistory.map((item) => (
              <div
                key={item.log_id}
                onClick={() => onSelectLog(item.log_id)}
                className="bg-gray-900/80 border border-gray-800 hover:border-gray-700 rounded-2xl p-5 transition-all duration-200 hover:shadow-xl hover:shadow-blue-900/10 cursor-pointer group flex flex-col justify-between"
              >
                <div>
                  {/* Top Bar: Exercise & Score Badge */}
                  <div className="flex items-start justify-between gap-2 mb-3">
                    <div>
                      <h4 className="text-base font-bold text-white group-hover:text-blue-400 transition-colors flex items-center gap-2">
                        <span>{item.exercise_name}</span>
                        {item.overlay_video_url && (
                          <span
                            title="Includes H.264 video overlay"
                            className="inline-flex items-center gap-1 text-[10px] bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded border border-blue-500/30"
                          >
                            <Play className="w-2.5 h-2.5 fill-blue-400" />
                            Video
                          </span>
                        )}
                      </h4>
                      <div className="flex items-center gap-1.5 text-xs text-gray-500 mt-1">
                        <Calendar className="w-3.5 h-3.5" />
                        <span>{formatDate(item.created_at)}</span>
                      </div>
                    </div>
                    {getScoreBadge(item.overall_score)}
                  </div>

                  {/* Key Metrics Grid */}
                  <div className="grid grid-cols-3 gap-2 bg-gray-800/50 border border-gray-800/80 rounded-xl p-2.5 my-3 text-center">
                    <div>
                      <div className="text-[10px] text-gray-400 uppercase font-semibold">Reps</div>
                      <div className="text-sm font-bold text-white font-mono mt-0.5">
                        {item.total_reps > 0 ? item.total_reps : '—'}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] text-gray-400 uppercase font-semibold">Flare</div>
                      <div className="text-sm font-bold text-indigo-400 font-mono mt-0.5">
                        {item.avg_elbow_flare > 0 ? `${Math.round(item.avg_elbow_flare)}°` : '—'}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] text-gray-400 uppercase font-semibold">Tempo</div>
                      <div className="text-sm font-bold text-amber-400 font-mono mt-0.5">
                        {item.avg_eccentric_tempo > 0 ? `${item.avg_eccentric_tempo.toFixed(1)}s` : '—'}
                      </div>
                    </div>
                  </div>

                  {/* Primary Flaw / Note */}
                  {item.primary_flaw && (
                    <div className="text-xs text-gray-300 bg-gray-800/30 border border-gray-800 rounded-lg p-2 flex items-start gap-1.5 mb-3">
                      <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                      <span className="line-clamp-2 text-[11px] leading-snug">{item.primary_flaw}</span>
                    </div>
                  )}
                </div>

                {/* Footer Controls */}
                <div className="pt-3 border-t border-gray-800/80 flex items-center justify-between text-xs">
                  <span className="text-blue-400 group-hover:underline font-medium flex items-center gap-1">
                    <span>View Breakdown</span>
                    <span>→</span>
                  </span>
                  <button
                    onClick={(e) => handleDelete(e, item.workout_id, item.log_id)}
                    disabled={deletingId === item.workout_id}
                    title="Delete session"
                    className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>

              </div>
            ))}
          </div>

        </div>
        </>
      )}

    </div>
  );
}
