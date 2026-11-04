import { useState } from 'react';
import {
  EyeOff,
  FolderPlus,
  Loader2,
  Plus,
  Radio,
  Settings2,
  SlidersHorizontal,
  Sparkles,
  Tag,
  Upload,
  X,
} from 'lucide-react';

const FOCUS_SUGGESTIONS = [
  'react',
  'typescript',
  'javascript',
  'node.js',
  'python',
  'postgresql',
  'supabase',
  'next.js',
  'tailwind',
  'graphql',
  'aws',
  'docker',
  'kubernetes',
  'llm',
  'ai agent',
  'data engineering',
  'remote',
];

function KeywordChip({ type, item, onDelete }) {
  const focus = type === 'focus';
  return (
    <span
      className={[
        'group inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-medium transition-all duration-200',
        focus
          ? 'border-cyan-400/20 bg-cyan-400/[0.08] text-cyan-100 shadow-[0_0_20px_-10px_rgba(34,211,238,0.8)] hover:border-cyan-300/40 hover:bg-cyan-400/[0.13]'
          : 'border-rose-400/20 bg-rose-500/[0.08] text-rose-200 shadow-[0_0_20px_-12px_rgba(251,113,133,0.7)] hover:border-rose-300/40 hover:bg-rose-500/[0.13]',
        item.enabled ? '' : 'opacity-45 saturate-50',
      ].join(' ')}
    >
      {focus ? <Tag className="h-3 w-3 opacity-60" /> : <EyeOff className="h-3 w-3 opacity-60" />}
      <span className="max-w-[180px] truncate">{item.value}</span>
      {!item.enabled && (
        <span className="rounded bg-white/5 px-1 py-0.5 text-[8px] font-semibold uppercase tracking-wider text-slate-400">
          paused
        </span>
      )}
      <button
        type="button"
        aria-label={`Delete ${item.value}`}
        title={`Delete ${item.value}`}
        onClick={() => onDelete(type, item.value)}
        className="ml-0.5 rounded p-0.5 text-current opacity-35 transition hover:bg-white/10 hover:opacity-100"
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}

function KeywordSection({ type, title, subtitle, items, onAdd, onDelete, onManage }) {
  const [value, setValue] = useState('');
  const [group, setGroup] = useState('');
  const [adding, setAdding] = useState(false);
  const focus = type === 'focus';
  const existingGroups = [...new Set(items.map((item) => item.group).filter(Boolean))];

  const submit = async (event) => {
    event.preventDefault();
    const clean = value.trim().toLowerCase();
    if (!clean || adding) return;
    const typedGroup = group.trim().slice(0, 40);
    const cleanGroup = typedGroup
      ? existingGroups.find((name) => name.toLowerCase() === typedGroup.toLowerCase()) || typedGroup
      : '';
    setAdding(true);
    const ok = await onAdd(type, clean, cleanGroup);
    setAdding(false);
    if (ok) {
      setValue('');
      setGroup('');
    }
  };

  return (
    <section className="min-w-0">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-[13px] font-semibold text-slate-200">
            {focus ? (
              <Sparkles className="h-3.5 w-3.5 text-cyan-300" />
            ) : (
              <EyeOff className="h-3.5 w-3.5 text-rose-300" />
            )}
            {title}
          </h3>
          <p className="mt-1 text-[11px] leading-relaxed text-slate-500">{subtitle}</p>
        </div>
        <button type="button" onClick={() => onManage(type)} className="btn btn-ghost btn-xs shrink-0">
          <Settings2 className="h-3 w-3" />
          Manage
        </button>
      </div>

      <div className="chip-grid" role="list" aria-label={`${title} keywords`}>
        {items.length ? (
          items.map((item) => (
            <span role="listitem" key={item.value}>
              <KeywordChip type={type} item={item} onDelete={onDelete} />
            </span>
          ))
        ) : (
          <span className="text-[11px] italic text-slate-600">No {focus ? 'highlight' : 'hide'} keywords yet.</span>
        )}
      </div>

      <form onSubmit={submit} className="mt-3 space-y-2">
        <div className="flex items-center gap-2">
          <div className="relative min-w-0 flex-1">
            <Plus className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-600" />
            <input
              type="text"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              list={focus ? 'focus-keyword-suggestions' : undefined}
              placeholder={focus ? 'Add a highlight keyword...' : 'Add a hide keyword...'}
              className={`input-dark pl-8 ${focus ? 'focus:border-cyan-400/40 focus:ring-cyan-400/10' : 'focus:border-rose-400/40 focus:ring-rose-400/10'}`}
            />
            {focus && (
              <datalist id="focus-keyword-suggestions">
                {FOCUS_SUGGESTIONS.map((suggestion) => (
                  <option value={suggestion} key={suggestion} />
                ))}
              </datalist>
            )}
          </div>
          <button
            type="submit"
            disabled={adding || !value.trim()}
            className={`btn btn-xs shrink-0 ${focus ? 'btn-primary' : 'btn-danger-soft'}`}
          >
            {adding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
            Add
          </button>
        </div>

        <div className="relative">
          <FolderPlus className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-600" />
          <input
            type="text"
            value={group}
            onChange={(event) => setGroup(event.target.value.slice(0, 40))}
            list={`${type}-group-suggestions`}
            placeholder="Group (optional) — e.g. Frontend, Leadership"
            aria-label={`Group for new ${focus ? 'highlight' : 'hide'} keyword`}
            className="input-dark h-8 pl-8 text-[10px]"
          />
          <datalist id={`${type}-group-suggestions`}>
            {existingGroups.map((name) => (
              <option value={name} key={name} />
            ))}
          </datalist>
        </div>
      </form>
    </section>
  );
}

export default function PreferencesPanel({
  filters,
  activeFocus,
  activeExclude,
  pausedCount,
  onAddKeyword,
  onDeleteKeyword,
  onManageKeywords,
  onOpenLocalSources,
  onOpenProfile,
  onOpenWeights,
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
            Scrapers fetch a broad set of roles. Your keywords shape what appears here, not what is fetched.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex items-center gap-2 rounded-lg border border-white/[0.07] bg-white/[0.025] px-2.5 py-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.8)]" />
            <span className="text-[10px] font-medium text-slate-400">
              <span className="font-semibold text-cyan-200">{activeFocus}</span> highlight
              <span className="mx-1 text-slate-700">/</span>
              <span className="font-semibold text-rose-200">{activeExclude}</span> hide active
            </span>
            {pausedCount > 0 && (
              <span className="text-[9px] text-slate-600">({pausedCount} paused)</span>
            )}
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onOpenWeights}>
            <SlidersHorizontal className="h-3.5 w-3.5" />
            Keyword weights
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

      <div className="relative mt-5 grid gap-6 border-t border-white/[0.06] pt-5 xl:grid-cols-2 xl:gap-10">
        <KeywordSection
          type="focus"
          title="Highlight keywords"
          subtitle="Matching roles get a cyan outline and glow."
          items={filters.focus}
          onAdd={onAddKeyword}
          onDelete={onDeleteKeyword}
          onManage={onManageKeywords}
        />
        <KeywordSection
          type="exclude"
          title="Hide keywords"
          subtitle="Matching roles disappear from the results."
          items={filters.exclude}
          onAdd={onAddKeyword}
          onDelete={onDeleteKeyword}
          onManage={onManageKeywords}
        />
      </div>
    </section>
  );
}
