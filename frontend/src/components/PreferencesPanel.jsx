import {
  EyeOff,
  Radio,
  Settings2,
  SlidersHorizontal,
  Sparkles,
  Upload,
} from 'lucide-react';

function countEnabled(items) {
  return items.filter((item) => item.enabled).length;
}

function ScopeSummary({ name, keywords, active, onManage }) {
  const focus = keywords?.focus || [];
  const exclude = keywords?.exclude || [];
  const activeFocus = countEnabled(focus);
  const activeExclude = countEnabled(exclude);
  const paused = focus.length + exclude.length - activeFocus - activeExclude;
  const preview = focus.filter((item) => item.enabled).slice(0, 4);

  return (
    <button
      type="button"
      onClick={() => onManage(name)}
      className={`group min-w-0 rounded-xl border px-3.5 py-3 text-left transition ${
        active
          ? 'border-cyan-400/20 bg-cyan-400/[0.05] shadow-[0_0_40px_-24px_rgba(34,211,238,0.7)]'
          : 'border-white/[0.06] bg-white/[0.015] hover:border-white/[0.12] hover:bg-white/[0.03]'
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className={`h-1.5 w-1.5 rounded-full ${active ? 'bg-cyan-400' : 'bg-slate-600'}`} />
        <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-300">
          {name}
        </span>
        {active && (
          <span className="rounded bg-cyan-400/10 px-1.5 py-0.5 text-[8px] font-semibold uppercase tracking-wider text-cyan-200/80">
            current tab
          </span>
        )}
        <Settings2 className="ml-auto h-3 w-3 text-slate-600 transition group-hover:text-slate-300" />
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-slate-500">
        <span>
          <span className="font-semibold text-cyan-200">{activeFocus}</span> highlight
        </span>
        <span>
          <span className="font-semibold text-rose-200">{activeExclude}</span> hide
        </span>
        {paused > 0 && <span className="text-slate-600">{paused} paused</span>}
      </div>

      <div className="mt-2 flex flex-wrap gap-1">
        {preview.length ? (
          preview.map((item) => (
            <span
              key={item.value}
              className="max-w-[110px] truncate rounded border border-cyan-400/15 bg-cyan-400/[0.06] px-1.5 py-0.5 text-[9px] text-cyan-100/80"
            >
              {item.value}
            </span>
          ))
        ) : (
          <span className="text-[9px] italic text-slate-600">No highlight keywords yet.</span>
        )}
        {focus.filter((item) => item.enabled).length > preview.length && (
          <span className="rounded border border-white/[0.06] px-1.5 py-0.5 text-[9px] text-slate-500">
            +{focus.filter((item) => item.enabled).length - preview.length}
          </span>
        )}
      </div>
    </button>
  );
}

export default function PreferencesPanel({
  keywords,
  activeScope,
  onManageKeywords,
  onOpenLocalSources,
  onOpenProfile,
}) {
  return (
    <section className="glass-panel relative overflow-hidden px-5 py-5 sm:px-6">
      <div className="pointer-events-none absolute right-0 top-0 h-40 w-72 rounded-full bg-blue-500/[0.05] blur-3xl" />

      <div className="relative flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-cyan-400/15 bg-cyan-400/[0.07]">
              <Sparkles className="h-3.5 w-3.5 text-cyan-300" />
            </span>
            <h2 className="text-[15px] font-semibold tracking-tight text-slate-100">Keywords & Preferences</h2>
          </div>
          <p className="mt-2 max-w-2xl text-[11px] leading-relaxed text-slate-500">
            Global and Local each have their own highlight, hide and scoring keywords. Weights are
            shared, so the same scale ranks both feeds. The active dashboard tab uses its own set.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn btn-primary btn-sm" onClick={() => onManageKeywords(activeScope)}>
            <SlidersHorizontal className="h-3.5 w-3.5" />
            Keywords & weights
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onOpenLocalSources}>
            <Radio className="h-3.5 w-3.5" />
            Local Sources
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onOpenProfile}>
            <Upload className="h-3.5 w-3.5" />
            Import from CV
          </button>
        </div>
      </div>

      <div className="relative mt-5 grid gap-2.5 border-t border-white/[0.06] pt-5 sm:grid-cols-2">
        <ScopeSummary
          name="global"
          keywords={keywords.global}
          active={activeScope === 'global'}
          onManage={onManageKeywords}
        />
        <ScopeSummary
          name="local"
          keywords={keywords.local}
          active={activeScope === 'local'}
          onManage={onManageKeywords}
        />
      </div>

      <div className="relative mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[9px] text-slate-600">
        <span className="inline-flex items-center gap-1">
          <Sparkles className="h-2.5 w-2.5 text-cyan-300/60" />
          Highlight keywords outline matching cards
        </span>
        <span className="inline-flex items-center gap-1">
          <EyeOff className="h-2.5 w-2.5 text-rose-300/60" />
          Hide keywords remove matching cards
        </span>
        <span>Paused keywords stay saved but stop scoring until resumed.</span>
      </div>
    </section>
  );
}
