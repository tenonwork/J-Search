import { useEffect } from 'react';
import { CheckCircle2 } from 'lucide-react';

export default function Toast({ toast, onDismiss }) {
  useEffect(() => {
    if (!toast) return undefined;
    const delay = toast.action ? 6000 : 2400;
    const timer = setTimeout(onDismiss, delay);
    return () => clearTimeout(timer);
  }, [toast, onDismiss]);

  if (!toast) return null;

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-5 z-[100] flex justify-center px-4">
      <div className="pointer-events-auto flex max-w-[92vw] animate-fade-up items-center gap-2.5 rounded-xl border border-white/[0.1] bg-[#0d1320]/95 px-4 py-2.5 shadow-[0_20px_60px_-15px_rgba(0,0,0,0.9)] backdrop-blur-xl">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-cyan-400/10">
          <CheckCircle2 className="h-3.5 w-3.5 text-cyan-300" />
        </span>
        <span className="text-[11px] font-medium text-slate-200">{toast.message}</span>
        {toast.action && (
          <button
            type="button"
            onClick={() => {
              toast.action.handler();
              onDismiss();
            }}
            className="ml-2 rounded-md border border-cyan-400/20 bg-cyan-400/[0.08] px-2 py-1 text-[10px] font-semibold text-cyan-200 transition hover:bg-cyan-400/[0.14]"
          >
            {toast.action.label}
          </button>
        )}
      </div>
    </div>
  );
}
