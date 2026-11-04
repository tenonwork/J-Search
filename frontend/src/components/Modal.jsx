import { useEffect } from 'react';
import { X } from 'lucide-react';

const SIZES = {
  sm: 'max-w-md',
  md: 'max-w-2xl',
  lg: 'max-w-3xl',
  xl: 'max-w-5xl',
};

export default function Modal({
  title,
  eyebrow,
  onClose,
  children,
  footer,
  size = 'md',
  icon: Icon,
  bodyClassName = '',
}) {
  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center p-0 sm:items-center sm:p-5" role="presentation">
      <div
        className="absolute inset-0 bg-[#050810]/80 backdrop-blur-md"
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) onClose();
        }}
      />
      <div
        className={`relative flex max-h-[92vh] w-full ${SIZES[size]} animate-scale-in flex-col overflow-hidden rounded-t-2xl border border-white/[0.09] bg-[#0d1320]/95 shadow-[0_40px_120px_-20px_rgba(0,0,0,0.9)] sm:rounded-2xl`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-300/50 to-transparent" />
        <div className="flex items-start justify-between gap-4 border-b border-white/[0.07] px-5 py-4 sm:px-6">
          <div className="flex min-w-0 items-start gap-3">
            {Icon && (
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-cyan-400/15 bg-cyan-400/[0.07]">
                <Icon className="h-4 w-4 text-cyan-300" />
              </span>
            )}
            <div className="min-w-0">
              {eyebrow && (
                <p className="mb-0.5 text-[9px] font-semibold uppercase tracking-[0.2em] text-cyan-300/70">
                  {eyebrow}
                </p>
              )}
              <h2 className="truncate text-[15px] font-semibold tracking-tight text-slate-100">{title}</h2>
            </div>
          </div>
          <button type="button" onClick={onClose} className="icon-btn shrink-0" aria-label="Close dialog">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className={`min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-6 ${bodyClassName}`}>{children}</div>

        {footer && (
          <div className="flex flex-wrap items-center justify-end gap-2 border-t border-white/[0.07] bg-white/[0.015] px-5 py-3.5 sm:px-6">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
