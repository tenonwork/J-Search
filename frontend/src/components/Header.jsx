import { CheckCircle2, EyeOff, Globe2, LocateFixed, Play, Sparkles } from 'lucide-react';
import Logo from './Logo';

function runScrapers(mode) {
  window.location.href = `/run?mode=${mode}`;
}

export default function Header({ appliedCount, hiddenCount }) {
  return (
    <header className="glass-panel relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-24 -top-32 h-72 w-72 rounded-full bg-cyan-400/10 blur-3xl" />
        <div className="absolute left-1/3 -top-40 h-80 w-96 rounded-full bg-blue-600/15 blur-3xl" />
        <div className="absolute -right-20 top-0 h-64 w-64 rounded-full bg-cyan-300/[0.06] blur-3xl" />
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-300/40 to-transparent" />
      </div>

      <div className="relative flex flex-col gap-6 px-5 py-6 sm:px-7 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex items-center gap-4">
          <Logo className="h-[54px] w-[54px] shrink-0 drop-shadow-[0_0_18px_rgba(34,211,238,0.18)]" />
          <div className="min-w-0">
            <div className="flex items-baseline gap-0.5">
              <h1 className="text-[27px] font-semibold leading-none tracking-[-0.045em] text-white sm:text-[31px]">
                <span className="bg-gradient-to-r from-cyan-300 via-sky-400 to-blue-500 bg-clip-text text-transparent">
                  J
                </span>
                <span className="text-slate-100">-Search</span>
              </h1>
              <Sparkles className="ml-2 h-3.5 w-3.5 text-cyan-300/70" />
            </div>
            <p className="mt-2 text-[9px] font-semibold uppercase tracking-[0.32em] text-slate-500 sm:text-[10px]">
              Your digital navigator
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-4 sm:flex-row sm:items-center xl:justify-end">
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="btn btn-primary" onClick={() => runScrapers('all')}>
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-white/75 opacity-75 motion-reduce:hidden" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-white" />
              </span>
              <Play className="h-3.5 w-3.5 fill-current" />
              Run All Scrapers
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => runScrapers('global')}>
              <Globe2 className="h-3.5 w-3.5" />
              Run Global Only
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => runScrapers('local')}>
              <LocateFixed className="h-3.5 w-3.5" />
              Run Local Only
            </button>
          </div>

          <div className="flex items-center gap-2">
            <a href="/applied" className="stat-pill group">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-300/80" />
              <span className="text-slate-400 group-hover:text-slate-300">Applied</span>
              <span className="tabular-nums text-sm font-semibold text-slate-100">{appliedCount}</span>
            </a>
            <a href="/hidden" className="stat-pill group">
              <EyeOff className="h-3.5 w-3.5 text-rose-300/80" />
              <span className="text-slate-400 group-hover:text-slate-300">Hidden</span>
              <span className="tabular-nums text-sm font-semibold text-slate-100">{hiddenCount}</span>
            </a>
          </div>
        </div>
      </div>
    </header>
  );
}
