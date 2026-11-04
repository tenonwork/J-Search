import { Sparkles } from 'lucide-react';

export default function ImpactPreview({ impact, strictness, actionLabel = 'saving' }) {
  if (!impact) return null;
  const before = Number(impact.before) || 0;
  const after = Number(impact.after) || 0;
  const labels = { strict: 'Strict', balanced: 'Balanced', lenient: 'Lenient' };

  return (
    <div className="rounded-xl border border-cyan-400/10 bg-cyan-400/[0.035] px-4 py-3.5">
      <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-cyan-300/70">
        <Sparkles className="h-3 w-3" />
        Impact preview
      </div>
      <p className="mt-1.5 text-[12px] text-slate-400">
        <span className="font-semibold tabular-nums text-slate-200">{before}</span> jobs visible now
        <span className="mx-1.5 text-slate-700">→</span>
        <span className="font-semibold tabular-nums text-cyan-200">{after}</span> after {actionLabel}
        <span className="text-slate-600"> ({labels[strictness] || 'Balanced'})</span>
      </p>
      <div className="mt-1 space-y-0.5 text-[10px] text-slate-500">
        {impact.hidden_by_exclude > 0 && (
          <p className="text-rose-300/80">{impact.hidden_by_exclude} hidden by the new hide keywords.</p>
        )}
        {impact.hidden_by_score > 0 && (
          <p>{impact.hidden_by_score} drop out because of scoring changes.</p>
        )}
        {impact.newly_visible > 0 && <p>{impact.newly_visible} become visible again.</p>}
        {impact.newly_highlighted > 0 && <p>{impact.newly_highlighted} will get a highlight outline.</p>}
      </div>
    </div>
  );
}
