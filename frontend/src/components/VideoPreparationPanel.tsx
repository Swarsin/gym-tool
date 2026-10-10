import { Loader2, Scissors, AlertCircle } from 'lucide-react';
import type { UploadState } from '../lib/videoUploadController';

interface Props {
  state: UploadState;
  onCancel: () => void;
  onRetry: () => void;
  onServerFallback: () => void;
}

export default function VideoPreparationPanel({ state, onCancel, onRetry, onServerFallback }: Props) {
  const fallback = state.phase === 'fallback';
  const percent = Math.round(state.progress * 100);
  return (
    <div className="bg-gray-900/80 border border-gray-800 rounded-2xl p-6 sm:p-8 max-w-2xl mx-auto space-y-5">
      <div className="flex items-center gap-3 text-blue-400">
        {fallback ? <AlertCircle className="w-6 h-6 text-amber-300" /> : <Scissors className="w-6 h-6" />}
        <h3 className="text-xl font-bold text-white">{fallback ? 'On-device trimming unavailable' : 'Preparing selected clip'}</h3>
      </div>
      {fallback ? (
        <>
          <p role="alert" className="text-sm text-amber-300">{state.error}</p>
          <p className="text-sm text-gray-400">Nothing has been uploaded. Server trimming uploads the entire original recording and applies your selected range there.</p>
          <div className="flex flex-wrap gap-3">
            <button onClick={onRetry} className="px-4 py-2 rounded-lg bg-gray-800 text-white text-sm">Retry on device</button>
            <button onClick={onServerFallback} className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm">Upload original &amp; trim on server</button>
          </div>
        </>
      ) : (
        <>
          <p className="text-sm text-gray-400">Trimming your {state.selectedDuration?.toFixed(1)}-second selection on this device before uploading. Keep this tab open.</p>
          <div role="progressbar" aria-label="Clip preparation" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}
            className="h-2 rounded-full overflow-hidden bg-gray-800">
            <div className="h-full bg-blue-500 transition-all" style={{ width: `${percent}%` }} />
          </div>
          <p className="flex items-center gap-2 text-xs text-blue-300"><Loader2 className="w-4 h-4 animate-spin" />{percent}% prepared</p>
        </>
      )}
      <button onClick={onCancel} className="text-sm text-gray-400 hover:text-white underline">Cancel and return home</button>
    </div>
  );
}
