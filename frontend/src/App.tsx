import { useState, useEffect } from 'react';
import {
  BarChart2,
  Upload,
  User as UserIcon,
  LogIn,
  LogOut,
  Plus,
  Loader2,
  Activity,
  ChevronRight,
  Menu,
  X,
  AlertTriangle
} from 'lucide-react';
import UploadZone from './components/UploadZone';
import PipelineMonitor from './components/PipelineMonitor';
import VideoPreparationPanel from './components/VideoPreparationPanel';
import ResultsPanel from './components/ResultsPanel';
import Dashboard from './components/Dashboard';
import AuthModal from './components/AuthModal';
import ToastContainer, { ToastMessage } from './components/Toast';
import { supabase } from './lib/supabase';
import { API_BASE_URL } from './lib/api';
import { useVideoUpload } from './hooks/useVideoUpload';

type TabView = 'analyze' | 'dashboard';
type AnalysisStatus = 'idle' | 'preparing' | 'uploading' | 'processing' | 'completed' | 'failed';

function App() {
  const [currentTab, setCurrentTab] = useState<TabView>('analyze');
  const [logId, setLogId] = useState<number | null>(null);
  const [analysisStatus, setAnalysisStatus] = useState<AnalysisStatus>('idle');
  const [resultsData, setResultsData] = useState<any>(null);
  const [loadingPastLog, setLoadingPastLog] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Auth States
  const [session, setSession] = useState<any>(null);
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Toasts
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [backendStatus, setBackendStatus] = useState<'unknown' | 'healthy' | 'degraded'>('unknown');

  const addToast = (toast: Omit<ToastMessage, 'id'>) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { ...toast, id }]);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const videoUpload = useVideoUpload((state) => {
    if (state.phase === 'preparing' || state.phase === 'fallback') {
      setErrorMessage(null);
      setLogId(null);
      setAnalysisStatus('preparing');
    } else if (state.phase === 'uploading') {
      setErrorMessage(null);
      setLogId(null);
      setAnalysisStatus('uploading');
    } else if (state.phase === 'processing') {
      setLogId(state.logId!);
      setAnalysisStatus('processing');
    } else if (state.phase === 'failed') {
      setErrorMessage(state.error || 'Video preparation or upload failed.');
      setAnalysisStatus('failed');
    } else {
      setAnalysisStatus('idle');
    }
  });

  useEffect(() => {
    const checkBackendHealth = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/v1/status`, { method: 'GET' });
        if (!res.ok) {
          setBackendStatus('degraded');
          return;
        }
        const data = await res.json();
        setBackendStatus(data.status === 'healthy' ? 'healthy' : 'degraded');
      } catch {
        setBackendStatus('degraded');
      }
    };

    checkBackendHealth();
    const healthInterval = window.setInterval(checkBackendHealth, 30000);

    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      if (session) {
        addToast({
          type: 'success',
          title: 'Authenticated',
          message: `Logged in as ${session.user.email}`,
        });
      }
    });

    return () => {
      window.clearInterval(healthInterval);
      subscription.unsubscribe();
    };
  }, []);

  const handleSelectPastLog = async (selectedLogId: number) => {
    videoUpload.controller.cancel(false);
    try {
      setLoadingPastLog(true);
      setLogId(selectedLogId);
      const headers: Record<string, string> = {};
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
      const res = await fetch(`${API_BASE_URL}/api/v1/results/${selectedLogId}`, { headers });
      if (!res.ok) throw new Error("Failed to load result");
      const data = await res.json();
      setResultsData(data);
      setAnalysisStatus('completed');
      setCurrentTab('analyze');
      addToast({
        type: 'info',
        title: 'Loaded Session',
        message: `Loaded analysis for Log #${selectedLogId}`,
      });
    } catch (err: any) {
      console.error("Error loading past result:", err);
      addToast({
        type: 'error',
        title: 'Load Failed',
        message: 'Could not retrieve past workout data.',
      });
    } finally {
      setLoadingPastLog(false);
    }
  };

  const handleSignOut = async () => {
    videoUpload.controller.cancel();
    await supabase.auth.signOut();
    addToast({
      type: 'info',
      title: 'Signed Out',
      message: 'You have been signed out.',
    });
  };

  const userId = session?.user?.id;
  const userEmail = session?.user?.email;
  const accessToken = session?.access_token;

  return (
    <div className="min-h-screen bg-[#0b0f19] text-gray-100 flex flex-col selection:bg-blue-600 selection:text-white">
      
      {/* Toast Notifications */}
      <ToastContainer toasts={toasts} onDismiss={removeToast} />

      {/* Global Navigation Header */}
      <header className="sticky top-0 z-40 bg-gray-900/80 backdrop-blur-md border-b border-gray-800">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          
          {/* Logo & Brand */}
          <button
            onClick={() => {
              videoUpload.controller.cancel(false);
              setCurrentTab('analyze');
              setAnalysisStatus('idle');
              setLogId(null);
              setResultsData(null);
              setErrorMessage(null);
            }}
            className="flex items-center gap-3 text-left group hover:opacity-90 transition-opacity"
            title="Return to Home / Upload"
          >
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-blue-600 to-teal-400 flex items-center justify-center shadow-lg shadow-blue-500/20 text-white font-black text-lg group-hover:scale-105 transition-transform">
              ⚡
            </div>
            <div>
              <span className="font-extrabold text-lg sm:text-xl tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-blue-400 via-teal-300 to-emerald-400">
                FormAI
              </span>
              <span className="hidden sm:inline-block ml-2 text-[10px] uppercase font-bold tracking-wider bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded-full border border-blue-500/20">
                VBT &amp; Biomechanics
              </span>
            </div>
          </button>

          {/* Desktop Tab Switcher */}
          <nav className="hidden md:flex items-center bg-gray-800/80 border border-gray-700/80 p-1 rounded-xl shadow-inner">
            <button
              onClick={() => setCurrentTab('analyze')}
              className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
                currentTab === 'analyze'
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-600/30'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700/50'
              }`}
            >
              <Activity className="w-4 h-4" />
              <span>Analyze Video</span>
            </button>
            <button
              onClick={() => setCurrentTab('dashboard')}
              className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
                currentTab === 'dashboard'
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-600/30'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700/50'
              }`}
            >
              <BarChart2 className="w-4 h-4" />
              <span>Performance Dashboard</span>
            </button>
          </nav>

          {/* Auth & Actions */}
          <div className="hidden sm:flex items-center gap-3">
            <div
              className={`flex items-center gap-2 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] ${
                backendStatus === 'healthy'
                  ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                  : backendStatus === 'degraded'
                    ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                    : 'border-gray-700 bg-gray-800/80 text-gray-400'
              }`}
            >
              <span className={`h-2 w-2 rounded-full ${backendStatus === 'healthy' ? 'bg-emerald-400' : backendStatus === 'degraded' ? 'bg-amber-400' : 'bg-gray-500'}`} />
              <span>{backendStatus === 'healthy' ? 'Backend online' : backendStatus === 'degraded' ? 'Backend slow' : 'Checking backend'}</span>
            </div>
            {session ? (
              <div className="flex items-center gap-2.5 bg-gray-800/90 border border-gray-700 rounded-xl px-3 py-1.5 shadow-sm">
                <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white font-bold text-xs">
                  {userEmail?.[0].toUpperCase()}
                </div>
                <span className="text-xs text-gray-200 font-medium max-w-[130px] truncate" title={userEmail}>
                  {userEmail}
                </span>
                <button
                  onClick={handleSignOut}
                  title="Sign Out"
                  className="text-gray-400 hover:text-red-400 p-1 rounded-lg hover:bg-gray-700/50 transition-colors ml-1"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <button
                onClick={() => setIsAuthOpen(true)}
                className="flex items-center gap-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white px-4 py-2 rounded-xl text-xs font-bold transition-all shadow-md shadow-blue-600/20"
              >
                <LogIn className="w-4 h-4" />
                <span>Sign In / Register</span>
              </button>
            )}
          </div>

          {/* Mobile Menu Button */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="sm:hidden p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-xl"
          >
            {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>

        </div>

        {/* Mobile Navigation Drawer */}
        {mobileMenuOpen && (
          <div className="sm:hidden border-t border-gray-800 bg-gray-900/95 px-4 py-4 space-y-3 animate-in slide-in-from-top-2">
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => {
                  setCurrentTab('analyze');
                  setMobileMenuOpen(false);
                }}
                className={`flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs font-bold ${
                  currentTab === 'analyze' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-300'
                }`}
              >
                <Activity className="w-4 h-4" />
                <span>Analyze</span>
              </button>
              <button
                onClick={() => {
                  setCurrentTab('dashboard');
                  setMobileMenuOpen(false);
                }}
                className={`flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs font-bold ${
                  currentTab === 'dashboard' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-300'
                }`}
              >
                <BarChart2 className="w-4 h-4" />
                <span>Dashboard</span>
              </button>
            </div>

            <div className="pt-2 border-t border-gray-800 space-y-2">
              <div
                className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.16em] ${
                  backendStatus === 'healthy'
                    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                    : backendStatus === 'degraded'
                      ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                      : 'border-gray-700 bg-gray-800/80 text-gray-400'
                }`}
              >
                <span className={`h-2 w-2 rounded-full ${backendStatus === 'healthy' ? 'bg-emerald-400' : backendStatus === 'degraded' ? 'bg-amber-400' : 'bg-gray-500'}`} />
                <span>{backendStatus === 'healthy' ? 'Backend online' : backendStatus === 'degraded' ? 'Backend slow' : 'Checking backend'}</span>
              </div>
              {session ? (
                <div className="flex items-center justify-between p-2 bg-gray-800 rounded-xl">
                  <span className="text-xs text-gray-300 truncate">{userEmail}</span>
                  <button
                    onClick={() => {
                      handleSignOut();
                      setMobileMenuOpen(false);
                    }}
                    className="text-xs text-red-400 font-semibold px-2 py-1 bg-red-500/10 rounded"
                  >
                    Sign Out
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => {
                    setIsAuthOpen(true);
                    setMobileMenuOpen(false);
                  }}
                  className="w-full py-2.5 bg-blue-600 text-white rounded-xl text-xs font-bold text-center"
                >
                  Sign In / Create Account
                </button>
              )}
            </div>
          </div>
        )}
      </header>

      {/* Main App Container */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 py-6 sm:py-8 space-y-8 pb-24 sm:pb-8">
        
        {/* Loading overlay for past log switching */}
        {loadingPastLog && (
          <div className="flex items-center justify-center p-12 bg-gray-900/60 border border-gray-800 rounded-2xl">
            <Loader2 className="w-6 h-6 animate-spin text-blue-400 mr-3" />
            <span className="text-gray-300 font-medium">Loading past workout data...</span>
          </div>
        )}

        {/* 1. ANALYZE TAB VIEW */}
        {!loadingPastLog && currentTab === 'analyze' && (
          <>
            {/* Idle / Upload View */}
            {analysisStatus === 'idle' && (
              <UploadZone
                userId={userId}
                accessToken={accessToken}
                onSubmit={(request) => { void videoUpload.controller.start(request); }}
                onShowToast={addToast}
              />
            )}

            {analysisStatus === 'preparing' && (
              <VideoPreparationPanel state={videoUpload.state}
                onCancel={() => videoUpload.controller.cancel()}
                onRetry={() => { void videoUpload.controller.retry(); }}
                onServerFallback={() => { void videoUpload.controller.useServerTrim(); }} />
            )}

            {/* Pipeline Monitor View */}
            {(analysisStatus === 'uploading' || analysisStatus === 'processing') && (
              <PipelineMonitor
                status={analysisStatus}
                logId={logId}
                accessToken={accessToken}
                uploadBytes={videoUpload.state.uploadBytes}
                onComplete={(data) => {
                  setResultsData(data);
                  setAnalysisStatus('completed');
                  addToast({
                    type: 'success',
                    title: 'Analysis Complete',
                    message: `Processed ${data.total_reps || 0} reps successfully.`,
                  });
                }}
                onCancel={() => {
                  videoUpload.controller.cancel(false);
                  setAnalysisStatus('idle');
                  setLogId(null);
                  setErrorMessage(null);
                  addToast({
                    type: 'info',
                    title: 'Cancelled',
                    message: 'Returned to home page.',
                  });
                }}
                onError={(err) => {
                  setErrorMessage(err || 'ML Pipeline failed to extract biomechanics.');
                  setAnalysisStatus('failed');
                  addToast({
                    type: 'error',
                    title: 'Processing Failed',
                    message: err || 'There was an error analyzing your video.',
                  });
                }}
              />
            )}

            {/* Results Panel View */}
            {analysisStatus === 'completed' && resultsData && (
              <div className="space-y-6">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-gray-900/40 border border-gray-800 p-4 rounded-2xl">
                  <span className="text-xs text-gray-400 font-medium">
                    Displaying results for Log #{logId}
                  </span>
                  <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
                    <button
                      onClick={() => setCurrentTab('dashboard')}
                      className="flex-1 sm:flex-none px-3.5 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-semibold rounded-xl border border-gray-700 transition-colors text-center"
                    >
                      View in Dashboard
                    </button>
                    <button
                      onClick={() => {
                        setAnalysisStatus('idle');
                        setLogId(null);
                        setResultsData(null);
                      }}
                      className="flex-1 sm:flex-none px-3.5 py-2 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-xl transition-colors shadow-md shadow-blue-600/20 flex items-center justify-center gap-1.5"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      <span>New Upload</span>
                    </button>
                  </div>
                </div>
                <ResultsPanel data={resultsData} onReset={() => {
                  setAnalysisStatus('idle');
                  setLogId(null);
                  setResultsData(null);
                }} />
              </div>
            )}

            {/* Failed Error Recovery View */}
            {analysisStatus === 'failed' && (
              <div className="bg-red-950/20 border border-red-500/40 rounded-2xl p-8 text-center max-w-xl mx-auto space-y-5 shadow-2xl animate-in fade-in duration-300">
                <div className="w-14 h-14 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center mx-auto text-red-400">
                  <AlertTriangle className="w-7 h-7" />
                </div>
                <div>
                  <h3 className="text-xl font-bold text-red-400">Analysis Stopped</h3>
                  <p className="text-gray-300 text-xs sm:text-sm mt-1 leading-relaxed">
                    {errorMessage || 'The biomechanics engine encountered an unexpected error while processing your video.'}
                  </p>
                  <p className="text-gray-500 text-xs mt-2">
                    Tip: For best results on mobile, upload a 5–15 second clip with clear lighting and full view of the lifter.
                  </p>
                </div>
                <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
                  <button
                    onClick={() => {
                      setAnalysisStatus('idle');
                      setLogId(null);
                      setErrorMessage(null);
                    }}
                    className="w-full sm:w-auto px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold transition-all shadow-lg shadow-blue-600/20 flex items-center justify-center gap-2"
                  >
                    <span>← Return to Home / Upload</span>
                  </button>
                  <button
                    onClick={() => {
                      setAnalysisStatus('idle');
                      setLogId(null);
                      setErrorMessage(null);
                      setCurrentTab('dashboard');
                    }}
                    className="w-full sm:w-auto px-5 py-2.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-xl text-xs font-bold transition-colors border border-gray-700"
                  >
                    Open Dashboard
                  </button>
                </div>
              </div>
            )}
          </>
        )}

        {/* 2. PERFORMANCE DASHBOARD TAB VIEW */}
        {!loadingPastLog && currentTab === 'dashboard' && (
          <Dashboard
            userId={userId}
            accessToken={accessToken}
            onSelectLog={handleSelectPastLog}
            onNewUpload={() => {
              setCurrentTab('analyze');
              setAnalysisStatus('idle');
            }}
            onShowToast={addToast}
          />
        )}

      </main>

      {/* Mobile Sticky Bottom Tab Bar */}
      <nav className="sm:hidden fixed bottom-0 left-0 right-0 z-40 bg-gray-900/95 backdrop-blur-xl border-t border-gray-800 px-4 py-2 flex items-center justify-around shadow-2xl">
        <button
          onClick={() => setCurrentTab('analyze')}
          className={`flex flex-col items-center gap-1 py-1 px-5 rounded-xl transition-all ${
            currentTab === 'analyze'
              ? 'text-blue-400 font-bold'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          <Activity className={`w-5 h-5 ${currentTab === 'analyze' ? 'stroke-[2.5]' : 'stroke-2'}`} />
          <span className="text-[11px]">Analyze</span>
        </button>

        <button
          onClick={() => setCurrentTab('dashboard')}
          className={`flex flex-col items-center gap-1 py-1 px-5 rounded-xl transition-all ${
            currentTab === 'dashboard'
              ? 'text-blue-400 font-bold'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          <BarChart2 className={`w-5 h-5 ${currentTab === 'dashboard' ? 'stroke-[2.5]' : 'stroke-2'}`} />
          <span className="text-[11px]">Dashboard</span>
        </button>
      </nav>

      {/* Auth Modal */}
      <AuthModal
        isOpen={isAuthOpen}
        onClose={() => setIsAuthOpen(false)}
      />

    </div>
  );
}

export default App;
