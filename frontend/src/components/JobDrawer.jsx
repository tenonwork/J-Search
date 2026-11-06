import { useEffect } from 'react';
import {
  AlertTriangle,
  ArrowUpRight,
  Building2,
  Check,
  MapPin,
  Sparkles,
  X,
} from 'lucide-react';
import ScoreRing from './ScoreRing';

export default function JobDrawer({ job, onClose, onApplied, onDismiss }) {
  useEffect(() => {
    if (!job) return undefined;
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
  }, [job, onClose]);

  if (!job) return null;

  const matches = job.matches || [];
  const redFlags = job.redFlags || [];
  const description = (job.desc || '').trim();

  return (
    <div className="fixed inset-0 z-[65]" role="presentation">
      <div className="absolute inset-0 bg-[#050810]/70 backdrop-blur-sm" onClick={onClose} />
      <aside
        className="absolute inset-y-0 right-0 flex w-full max-w-[580px] animate-slide-in flex-col border-l border-white/[0.09] bg-[#0b101b]/98 shadow-[-40px_0_100px_-20px_rgba(0,0,0,0.8)]"
        role="dialog"
        aria-modal="true"
        aria-label={`${job.title} details`}
      >
        <div className="pointer-events-none absolute inset-y-0 left-0 w-px bg-gradient-to-b from-transparent via-cyan-300/30 to-transparent" />

        <div className="flex items-start justify-between gap-4 border-b border-white/[0.07] px-5 py-5 sm:px-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="source-chip">{job.source === 'local' ? 'Local' : 'Global'}</span>
              <span className="text-[9px] font-semibold uppercase tracking-[0.18em] text-slate-600">
                Role details
              </span>
            </div>
            <h2 className="mt-2 text-xl font-semibold leading-snug tracking-[-0.025em] text-slate-100">
              {job.title}
            </h2>
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
              <span className="inline-flex items-center gap-1.5">
                <Building2 className="h-3 w-3 text-slate-600" />
                {job.company || 'Unknown company'}
              </span>
              <span className="hidden h-3 w-px bg-white/[0.08] sm:block" />
              <span className="inline-flex items-center gap-1.5">
                <MapPin className="h-3 w-3 text-slate-600" />
                {job.location || 'Location not listed'}
              </span>
            </div>
          </div>
          <button type="button" onClick={onClose} className="icon-btn shrink-0" aria-label="Close details">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="flex items-center justify-between gap-4 border-b border-white/[0.06] px-5 py-4 sm:px-6">
            <div>
              <p className="text-[9px] font-semibold uppercase tracking-[0.2em] text-slate-600">Match breakdown</p>
              <p className="mt-1 text-[11px] text-slate-500">
                {matches.length} matched signal{matches.length === 1 ? '' : 's'}
                {redFlags.length ? ` · ${redFlags.length} gap${redFlags.length === 1 ? '' : 's'}` : ''}
              </p>
            </div>
            <ScoreRing score={job.score} size="lg" />
          </div>

          <section className="px-5 py-5 sm:px-6">
            <h3 className="drawer-section-title">
              <Sparkles className="h-3.5 w-3.5 text-cyan-300" />
              Matched signals
            </h3>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {matches.length ? (
                matches.map((match) => (
                  <span key={`match-${match}`} className="tag-positive">
                    <Check className="h-2.5 w-2.5" />
                    {match}
                  </span>
                ))
              ) : (
                <span className="text-[11px] italic text-slate-600">No positive signals matched.</span>
              )}
            </div>
          </section>

          {redFlags.length > 0 && (
            <section className="border-t border-white/[0.06] px-5 py-5 sm:px-6">
              <h3 className="drawer-section-title">
                <AlertTriangle className="h-3.5 w-3.5 text-rose-300" />
                Gaps & red flags
              </h3>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {redFlags.map((flag) => (
                  <span key={`flag-${flag}`} className="tag-negative">
                    {flag}
                  </span>
                ))}
              </div>
            </section>
          )}

          <section className="border-t border-white/[0.06] px-5 py-5 sm:px-6">
            <h3 className="drawer-section-title">Role description</h3>
            {job.teaser && (
              <p className="mt-2 text-[11px] leading-relaxed text-amber-200/80">
                Teaser only. Open the original page before judging this role.
              </p>
            )}
            <div className="mt-3 whitespace-pre-wrap text-[12px] leading-[1.75] text-slate-400">
              {description || 'No description was captured for this role. Open the original posting for the full details.'}
            </div>
          </section>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-white/[0.07] bg-white/[0.015] px-5 py-4 sm:px-6">
          <a
            href={job.url || '#'}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-primary btn-sm"
          >
            Open original posting
            <ArrowUpRight className="h-3.5 w-3.5" />
          </a>
          <button type="button" className="btn btn-apply btn-sm" onClick={() => onApplied(job)}>
            <Check className="h-3.5 w-3.5" />
            Applied
          </button>
          <button type="button" className="btn btn-dismiss btn-sm" onClick={() => onDismiss(job)}>
            <X className="h-3.5 w-3.5" />
            Not for me
          </button>
        </div>
      </aside>
    </div>
  );
}
