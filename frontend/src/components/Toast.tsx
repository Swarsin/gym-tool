import React, { useEffect } from 'react';
import { CheckCircle2, AlertCircle, Info, AlertTriangle, X } from 'lucide-react';

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info' | 'warning';
  title: string;
  message?: string;
}

interface ToastContainerProps {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

export default function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none px-4 sm:px-0">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

function ToastItem({ toast, onDismiss }: { toast: ToastMessage; onDismiss: (id: string) => void }) {
  useEffect(() => {
    const timer = setTimeout(() => {
      onDismiss(toast.id);
    }, 4500);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  const getStyle = () => {
    switch (toast.type) {
      case 'success':
        return {
          bg: 'bg-gray-900 border-emerald-500/50',
          icon: <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />,
          title: 'text-emerald-400',
        };
      case 'error':
        return {
          bg: 'bg-gray-900 border-red-500/50',
          icon: <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />,
          title: 'text-red-400',
        };
      case 'warning':
        return {
          bg: 'bg-gray-900 border-amber-500/50',
          icon: <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />,
          title: 'text-amber-400',
        };
      default:
        return {
          bg: 'bg-gray-900 border-blue-500/50',
          icon: <Info className="w-5 h-5 text-blue-400 shrink-0" />,
          title: 'text-blue-400',
        };
    }
  };

  const style = getStyle();

  return (
    <div
      className={`pointer-events-auto border rounded-xl p-3.5 shadow-2xl backdrop-blur-md flex items-start gap-3 transition-all duration-200 animate-in slide-in-from-bottom-3 ${style.bg}`}
    >
      {style.icon}
      <div className="flex-1 min-w-0">
        <h4 className={`text-xs font-bold uppercase tracking-wider ${style.title}`}>
          {toast.title}
        </h4>
        {toast.message && (
          <p className="text-xs text-gray-300 mt-0.5 leading-snug">{toast.message}</p>
        )}
      </div>
      <button
        onClick={() => onDismiss(toast.id)}
        className="text-gray-400 hover:text-white p-0.5 rounded transition-colors"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
