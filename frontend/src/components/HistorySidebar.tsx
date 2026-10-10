import React, { useEffect, useState } from 'react';
import { X, History, Dumbbell, Play, Calendar, AlertCircle, Plus, RefreshCw, ChevronRight } from 'lucide-react';
import { API_BASE_URL } from '../lib/api';

interface HistoryItem {
  log_id: number;
  workout_id: number;
  exercise_name: string;
  created_at: string;
  total_reps: number;
  avg_eccentric_tempo: number;
  avg_elbow_flare: number;
  overall_score?: number;
  primary_flaw?: string;
  overlay_video_url?: string;
}

interface HistorySidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectLog: (logId: number) => void;
  onNewUpload: () => void;
  activeLogId: number | null;
  userId?: string;
}

export default function HistorySidebar({
  isOpen,
  onClose,
  onSelectLog,
  onNewUpload,
  activeLogId,
  userId,
}: HistorySidebarProps) {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      let url = `${API_BASE_URL}/api/v1/history`;
      if (userId) {
        url += `?user_id=${userId}`;
      }
      const res = await fetch(url);
      if (!res.ok) throw new Error('Failed to fetch history');
      const data = await res.json();
      setHistory(data);
    } catch (err: any) {
      console.error('History fetch error:', err);
      setError('Could not load history');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchHistory();
    }
  }, [isOpen, userId]);

  if (!isOpen) return null;

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

  const getScoreColor = (score?: number) => {
    if (!score) return 'bg-gray-700 text-gray-300 border-gray-600';
    if (score >= 7) return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
    if (score >= 5) return 'bg-amber-500/10 text-amber-400 border-amber-500/30';
    return 'bg-red-500/10 text-red-400 border-red-500/30';
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="absolute inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-md bg-gray-900 border-l border-gray-800 shadow-2xl flex flex-col">
          
          {/* Header */}
          <div className="p-6 border-b border-gray-800 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <History className="w-5 h-5 text-blue-400" />
              <h2 className="text-xl font-bold text-white">Workout History</h2>
              <span className="bg-blue-500/10 text-blue-400 text-xs font-semibold px-2 py-0.5 rounded-full border border-blue-500/20">
                {history.length}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={fetchHistory}
                title="Refresh history"
                className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              </button>
              <button
                onClick={onClose}
                className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* New Analysis Button */}
          <div className="p-4 border-b border-gray-800 bg-gray-900/50">
            <button
              onClick={() => {
                onNewUpload();
                onClose();
              }}
              className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-semibold flex items-center justify-center gap-2 transition-colors shadow-lg shadow-blue-600/20 text-sm"
            >
              <Plus className="w-4 h-4" />
              <span>Analyze New Workout</span>
            </button>
          </div>

          {/* History List */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {loading && history.length === 0 && (
              <div className="text-center py-12 text-gray-400 text-sm">
                <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-blue-400" />
                Loading submission history...
              </div>
            )}

            {error && (
              <div className="p-4 bg-red-900/20 border border-red-500/30 rounded-xl text-red-400 text-sm flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {!loading && history.length === 0 && !error && (
              <div className="text-center py-12 text-gray-500 text-sm space-y-3">
                <Dumbbell className="w-10 h-10 mx-auto text-gray-700" />
                <p>No past workout submissions found.</p>
                <p className="text-xs text-gray-600">Upload your first video to start tracking form score over time!</p>
              </div>
            )}

            {history.map((item) => {
              const isActive = activeLogId === item.log_id;

              return (
                <div
                  key={item.log_id}
                  onClick={() => {
                    onSelectLog(item.log_id);
                    onClose();
                  }}
                  className={`p-4 rounded-xl border transition-all cursor-pointer relative group ${
                    isActive
                      ? 'bg-blue-900/20 border-blue-500 shadow-md'
                      : 'bg-gray-800/60 border-gray-700/60 hover:bg-gray-800 hover:border-gray-600'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div>
                      <h4 className="font-semibold text-white text-sm group-hover:text-blue-400 transition-colors flex items-center gap-1.5">
                        <span>{item.exercise_name}</span>
                        {item.overlay_video_url && (
                          <span title="Includes pose overlay video" className="inline-flex items-center gap-1 text-[10px] bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded border border-blue-500/30">
                            <Play className="w-2.5 h-2.5" />
                            Overlay
                          </span>
                        )}
                      </h4>
                      <div className="flex items-center gap-1 text-xs text-gray-400 mt-1">
                        <Calendar className="w-3 h-3 text-gray-500" />
                        <span>{formatDate(item.created_at)}</span>
                      </div>
                    </div>

                    {/* Score Badge */}
                    {item.overall_score !== undefined && (
                      <div className={`px-2.5 py-1 rounded-lg text-xs font-bold border ${getScoreColor(item.overall_score)}`}>
                        {item.overall_score}/10
                      </div>
                    )}
                  </div>

                  {/* Details row */}
                  <div className="flex items-center justify-between text-xs text-gray-400 pt-2 border-t border-gray-700/40 mt-2">
                    <div className="flex items-center gap-3">
                      <span>Reps: <strong className="text-gray-200">{item.total_reps}</strong></span>
                      <span>Ecc: <strong className="text-gray-200">{item.avg_eccentric_tempo.toFixed(1)}s</strong></span>
                    </div>
                    <div className="flex items-center text-blue-400 text-xs font-medium opacity-0 group-hover:opacity-100 transition-opacity">
                      <span>View Results</span>
                      <ChevronRight className="w-3.5 h-3.5 ml-0.5" />
                    </div>
                  </div>

                  {/* Primary Flaw snippet */}
                  {item.primary_flaw && (
                    <div className="mt-2 text-xs text-red-400/90 truncate bg-red-950/20 px-2 py-1 rounded border border-red-900/30">
                      Flaw: {item.primary_flaw}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

        </div>
      </div>
    </div>
  );
}
