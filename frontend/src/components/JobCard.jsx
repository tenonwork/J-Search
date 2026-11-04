import {
  ArrowRight,
  Building2,
  Check,
  ExternalLink,
  MapPin,
  Sparkles,
  X,
} from 'lucide-react';
import ScoreRing from './ScoreRing';

export default function JobCard({ job, focused, onReview, onApplied, onDismiss }) {
  const matches = job.matches || [];
  const redFlags = job.redFlags || [];

  return (
    <article
      className={`job-card group ${focused ? 'job-card-focused' : ''}`}
      onClick={(event) => {
        if (event.target.closest('a, button')) return;
        onReview(job);
      }}
    >
      <div className="flex min-w-0 flex-1 flex-col gap-3.5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="source-chip">{job.source === 'local' ? 'Local' : 'Global'}</span>
              {focused && (
                <span className="inline-flex items-center gap-1 rounded-md border border-cyan-400/20 bg-cyan-400/[0.08] px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.14em] text-cyan-200">
                  <Sparkles className="h-2.5 w-2.5" />
                  Focus
                </span>
              )}
            </div>
            <h3 className="mt-2 text-[16px] font-semibold leading-snug tracking-[-0.015em] text-slate-100 transition-colors group-hover:text-white">
              {job.title || 'Untitled role'}
            </h3>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
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
          <div className="hidden sm:block">
            <ScoreRing score={job.score} />
          </div>
        </div>

        {(matches.length > 0 || redFlags.length > 0) && (
          <div className="flex flex-wrap items-center gap-1.5">
            {matches.slice(0, 10).map((match) => (
              <span key={`good-${match}`} className="tag-positive">
                {match}
              </span>
            ))}
            {redFlags.slice(0, 6).map((flag) => (
              <span key={`bad-${flag}`} className="tag-negative">
                {flag}
              </span>
            ))}
            {matches.length > 10 && (
              <span className="text-[10px] font-medium text-slate-600">+{matches.length - 10} more</span>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn btn-primary btn-sm" onClick={() => onReview(job)}>
            Review Entry
            <ArrowRight className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5" />
          </button>
          <button type="button" className="btn btn-apply btn-sm" onClick={() => onApplied(job)}>
            <Check className="h-3.5 w-3.5" />
            Applied
          </button>
          <button type="button" className="btn btn-dismiss btn-sm" onClick={() => onDismiss(job)}>
            <X className="h-3.5 w-3.5" />
            Not for me
          </button>
          <a
            href={job.url || '#'}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto hidden items-center gap-1.5 rounded-md px-2 py-1 text-[10px] font-medium text-slate-600 transition hover:bg-white/[0.04] hover:text-slate-300 sm:inline-flex"
            title="Open the original posting"
          >
            <ExternalLink className="h-3 w-3" />
            Original
          </a>
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-white/[0.05] pt-3 sm:hidden">
        <ScoreRing score={job.score} />
        <a
          href={job.url || '#'}
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-ghost btn-xs"
        >
          <ExternalLink className="h-3 w-3" />
          Original posting
        </a>
      </div>
    </article>
  );
}
